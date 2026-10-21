"""Event-driven automation engine for Valetudo Essentials."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import (
    Event,
    EventStateChangedData,
    HomeAssistant,
    State,
    callback,
)
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.device_registry import DeviceEntryType
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
)
from homeassistant.util import dt as dt_util

from .const import (
    ACTIVE_STATES,
    AUTOMATION_KEYS,
    CONF_AUTO_EMPTY_ENABLED,
    CONF_AUTO_EMPTY_ENTITY,
    CONF_AWAY_DELAY,
    CONF_AWAY_ENABLED,
    CONF_BATTERY_MIN,
    CONF_COMPLETION_ENABLED,
    CONF_COMPLETION_NOTIFY_SERVICE,
    CONF_ERROR_ENABLED,
    CONF_ERROR_NOTIFY_SERVICE,
    CONF_FAN_ENTITY,
    CONF_FAN_SPEED,
    CONF_HOME_ACTION,
    CONF_HOME_ENABLED,
    CONF_MAINTENANCE_ENABLED,
    CONF_MAINTENANCE_SENSORS,
    CONF_MAINTENANCE_THRESHOLD,
    CONF_MAINTENANCE_TIME,
    CONF_NOTIFY_SERVICE,
    CONF_POST_RUN_SERVICE,
    CONF_PRESENCE_ENTITY,
    CONF_QUIET_ACTION,
    CONF_QUIET_ENABLED,
    CONF_QUIET_END,
    CONF_QUIET_RESUME,
    CONF_QUIET_START,
    CONF_SCHEDULE_DAYS,
    CONF_SCHEDULE_ENABLED,
    CONF_SCHEDULE_ONLY_WHEN_AWAY,
    CONF_SCHEDULE_TIME,
    CONF_VACUUM_ENTITY,
    DEFAULT_OPTIONS,
    DOMAIN,
    INTERRUPTIBLE_STATES,
    NAME,
    STATE_ERROR,
    STATE_PAUSED,
    TERMINAL_STATES,
)
from .logic import (
    battery_ok,
    format_duration,
    format_number,
    in_time_window,
    is_active,
    is_parked,
    low_consumables,
    normalize_presence,
    parse_percentage,
    parse_time,
    split_service,
    weekday_allowed,
)

_LOGGER = logging.getLogger(__name__)

BATTERY_ENTITY_KEYWORDS = ("battery",)
CONSUMABLE_EXCLUDE_KEYWORDS = ("battery", "wifi", "wi-fi", "signal", "rssi")


def merged_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Return options merged over the built-in defaults."""
    result = dict(DEFAULT_OPTIONS)
    if options:
        result.update(options)
    return result


class ValetudoEssentialsEngine:
    """Run the built-in automations for one configured vacuum."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.options = merged_options(entry.options)
        self.vacuum_entity: str = entry.data[CONF_VACUUM_ENTITY]
        self._unsubs: list[Callable[[], None]] = []
        self._away_cancel: Callable[[], None] | None = None
        self._lock = asyncio.Lock()
        self._paused_by_quiet = False
        self._start_after_quiet = False
        self._run_in_progress = False
        self._suppress_completion = False
        self._run_started_at: datetime | None = None
        self._device_id: str | None = None

    @property
    def presence_entity(self) -> str:
        """Return the configured presence entity."""
        return str(self.options.get(CONF_PRESENCE_ENTITY) or "")

    @property
    def device_info(self) -> DeviceInfo:
        """Return device information for the helper switches."""
        info = DeviceInfo(
            identifiers={(DOMAIN, self.entry.entry_id)},
            name=NAME,
            manufacturer=NAME,
            model="Vacuum automation helpers",
            entry_type=DeviceEntryType.SERVICE,
        )
        device_id = self._vacuum_device_id()
        if device_id:
            if "via_device_id" in DeviceInfo.__annotations__:
                info["via_device_id"] = device_id
            else:
                info["via_device"] = device_id  # type: ignore[typeddict-unknown-key]
        return info

    async def async_setup(self) -> None:
        """Register listeners and time triggers."""
        entities = {self.vacuum_entity}
        if self.presence_entity:
            entities.add(self.presence_entity)
        self._unsubs.append(
            async_track_state_change_event(self.hass, entities, self._handle_state_change)
        )

        self._register_time(CONF_QUIET_START, self._async_quiet_start)
        self._register_time(CONF_QUIET_END, self._async_quiet_end)
        self._register_time(CONF_SCHEDULE_TIME, self._async_schedule)
        self._register_time(CONF_MAINTENANCE_TIME, self._async_maintenance)

        if self._in_quiet_window():
            state = self._vacuum_state()
            if state and is_active(state.state):
                self.hass.async_create_task(self._async_enforce_quiet(state))

    async def async_unload(self) -> None:
        """Remove all listeners and cancel pending timers."""
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()
        self._cancel_away_timer()

    def is_enabled(self, key: str) -> bool:
        """Return whether an automation switch is enabled."""
        return bool(self.options.get(key, False))

    @callback
    def set_enabled(self, key: str, enabled: bool) -> None:
        """Persist a runtime switch change."""
        if key not in AUTOMATION_KEYS:
            return
        self.options[key] = enabled
        self.hass.config_entries.async_update_entry(self.entry, options=dict(self.options))
        if key == CONF_AWAY_ENABLED and not enabled:
            self._cancel_away_timer()
        if key == CONF_QUIET_ENABLED:
            if not enabled:
                self._paused_by_quiet = False
                self._start_after_quiet = False
            elif self._in_quiet_window():
                state = self._vacuum_state()
                if state and is_active(state.state):
                    self.hass.async_create_task(self._async_enforce_quiet(state))

    # ------------------------------------------------------------------
    # State handling
    # ------------------------------------------------------------------

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        if entity_id not in (self.vacuum_entity, self.presence_entity):
            return
        old_state = event.data["old_state"]
        new_state = event.data["new_state"]
        if new_state is None:
            return
        self.hass.async_create_task(
            self._async_handle_state_change(entity_id, old_state, new_state)
        )

    async def _async_handle_state_change(
        self, entity_id: str, old_state: State | None, new_state: State
    ) -> None:
        async with self._lock:
            if entity_id == self.vacuum_entity:
                await self._async_vacuum_changed(old_state, new_state)
            else:
                await self._async_presence_changed(old_state, new_state)

    async def _async_vacuum_changed(self, old_state: State | None, new_state: State) -> None:
        old = old_state.state if old_state else None
        new = new_state.state

        if new in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            return

        if new in ACTIVE_STATES and old not in ACTIVE_STATES:
            self._run_in_progress = True
            self._suppress_completion = False
            self._run_started_at = dt_util.utcnow()
            await self._async_enforce_quiet(new_state)
            return

        if new == STATE_ERROR:
            if old != STATE_ERROR:
                await self._async_notify_error(new_state)
            self._run_in_progress = False
            self._run_started_at = None
            self._suppress_completion = False
            return

        if new in TERMINAL_STATES and old not in TERMINAL_STATES:
            if not self._run_in_progress:
                return
            suppress = self._suppress_completion
            started = self._run_started_at
            self._run_in_progress = False
            self._run_started_at = None
            self._suppress_completion = False
            self._paused_by_quiet = False
            if not suppress:
                await self._async_notify_completion(started)
            await self._async_post_run()

    async def _async_presence_changed(self, old_state: State | None, new_state: State) -> None:
        old_home = normalize_presence(old_state.state if old_state else None)
        new_home = normalize_presence(new_state.state)
        if new_home is None:
            return

        if new_home:
            self._cancel_away_timer()
            self._start_after_quiet = False
            self._paused_by_quiet = False
            if old_home is False and self.is_enabled(CONF_HOME_ENABLED):
                await self._async_arrive_home()
            return

        if old_home is True and self.is_enabled(CONF_AWAY_ENABLED):
            self._schedule_away_start()

    # ------------------------------------------------------------------
    # Away / home automations
    # ------------------------------------------------------------------

    def _schedule_away_start(self) -> None:
        self._cancel_away_timer()
        delay_minutes = max(0, int(self.options.get(CONF_AWAY_DELAY, 0) or 0))
        if delay_minutes == 0:
            self.hass.async_create_task(self._async_start_when_away())
            return
        self._away_cancel = async_call_later(self.hass, delay_minutes * 60, self._away_timer_fired)

    def _cancel_away_timer(self) -> None:
        if self._away_cancel is not None:
            self._away_cancel()
            self._away_cancel = None

    @callback
    def _away_timer_fired(self, _now: datetime) -> None:
        self._away_cancel = None
        self.hass.async_create_task(self._async_start_when_away())

    async def _async_start_when_away(self) -> None:
        async with self._lock:
            if not self.is_enabled(CONF_AWAY_ENABLED):
                return
            presence = self.hass.states.get(self.presence_entity)
            if normalize_presence(presence.state if presence else None) is not False:
                return
            await self._async_try_start("away")

    async def _async_arrive_home(self) -> None:
        state = self._vacuum_state()
        if state is None or state.state not in INTERRUPTIBLE_STATES:
            return

        action = str(self.options.get(CONF_HOME_ACTION, "return_to_base"))
        if action == "pause" and state.state not in ACTIVE_STATES:
            return

        if action in ("return_to_base", "stop") and self._run_in_progress:
            self._suppress_completion = True
        self._paused_by_quiet = False
        self._start_after_quiet = False
        await self._async_abort(action)

    async def _async_try_start(self, reason: str) -> bool:
        state = self._vacuum_state()
        if state is None or not is_parked(state.state):
            return False
        if not battery_ok(self._battery_level(), float(self.options[CONF_BATTERY_MIN])):
            return False
        if self._in_quiet_window():
            if reason == "away":
                self._start_after_quiet = True
            return False

        await self._async_apply_fan_speed()
        try:
            await self.hass.services.async_call(
                "vacuum",
                "start",
                {"entity_id": self.vacuum_entity},
                blocking=True,
            )
        except HomeAssistantError as err:
            _LOGGER.warning("Could not start %s: %s", self.vacuum_entity, err)
            return False
        return True

    # ------------------------------------------------------------------
    # Quiet hours
    # ------------------------------------------------------------------

    def _in_quiet_window(self) -> bool:
        if not self.is_enabled(CONF_QUIET_ENABLED):
            return False
        start = parse_time(self.options.get(CONF_QUIET_START))
        end = parse_time(self.options.get(CONF_QUIET_END))
        if start is None or end is None:
            return False
        return in_time_window(dt_util.now().time(), start, end)

    async def _async_enforce_quiet(self, state: State) -> None:
        if not self._in_quiet_window():
            return
        if state.state not in ACTIVE_STATES:
            return
        action = str(self.options.get(CONF_QUIET_ACTION, "pause"))
        await self._async_abort(action, quiet=True)

    async def _async_quiet_start(self, now: datetime) -> None:
        async with self._lock:
            if not self.is_enabled(CONF_QUIET_ENABLED):
                return
            start = parse_time(self.options.get(CONF_QUIET_START))
            end = parse_time(self.options.get(CONF_QUIET_END))
            if start is None or end is None:
                return
            if not in_time_window(now.time(), start, end):
                return
            state = self._vacuum_state()
            if state is not None:
                await self._async_enforce_quiet(state)

    async def _async_quiet_end(self, _now: datetime) -> None:
        async with self._lock:
            if not self.is_enabled(CONF_QUIET_ENABLED):
                return
            start = parse_time(self.options.get(CONF_QUIET_START))
            end = parse_time(self.options.get(CONF_QUIET_END))
            if start is not None and end is not None:
                if in_time_window(dt_util.now().time(), start, end):
                    return

            resume = bool(self.options.get(CONF_QUIET_RESUME, True))
            state = self._vacuum_state()
            if (
                self._paused_by_quiet
                and resume
                and state is not None
                and state.state == STATE_PAUSED
            ):
                try:
                    await self.hass.services.async_call(
                        "vacuum",
                        "start",
                        {"entity_id": self.vacuum_entity},
                        blocking=True,
                    )
                except HomeAssistantError as err:
                    _LOGGER.warning(
                        "Could not resume %s after quiet hours: %s",
                        self.vacuum_entity,
                        err,
                    )
            self._paused_by_quiet = False

            if self._start_after_quiet:
                self._start_after_quiet = False
                if self.is_enabled(CONF_AWAY_ENABLED):
                    presence = self.hass.states.get(self.presence_entity)
                    if normalize_presence(presence.state if presence else None) is False:
                        await self._async_try_start("away")

    # ------------------------------------------------------------------
    # Schedule and maintenance
    # ------------------------------------------------------------------

    async def _async_schedule(self, now: datetime) -> None:
        async with self._lock:
            if not self.is_enabled(CONF_SCHEDULE_ENABLED):
                return
            days = self.options.get(CONF_SCHEDULE_DAYS) or []
            if not weekday_allowed(now.weekday(), days):
                return
            if self.options.get(CONF_SCHEDULE_ONLY_WHEN_AWAY):
                presence = self.hass.states.get(self.presence_entity)
                if normalize_presence(presence.state if presence else None) is not False:
                    return
            await self._async_try_start("schedule")

    async def _async_maintenance(self, _now: datetime) -> None:
        async with self._lock:
            if not self.is_enabled(CONF_MAINTENANCE_ENABLED):
                return
            threshold = float(self.options[CONF_MAINTENANCE_THRESHOLD])
            values: dict[str, Any] = {}
            names: dict[str, str] = {}
            for entity_id in self.maintenance_entities():
                state = self.hass.states.get(entity_id)
                if state is None:
                    continue
                values[entity_id] = state.state
                names[entity_id] = self._entity_name(entity_id, state)
            low = low_consumables(values, threshold)
            if not low:
                return
            lines = [
                f"- {names[entity_id]}: {format_number(value)}%" for entity_id, value in sorted(low)
            ]
            message = "The following consumables are running low:\n" + "\n".join(lines)
            await self._async_notify(
                "maintenance",
                "Vacuum maintenance due",
                message,
            )

    # ------------------------------------------------------------------
    # Notifications and post-run actions
    # ------------------------------------------------------------------

    async def _async_notify_error(self, state: State) -> None:
        if not self.is_enabled(CONF_ERROR_ENABLED):
            return
        details = (
            state.attributes.get("error_description")
            or state.attributes.get("error")
            or state.attributes.get("status")
        )
        message = f"{self._vacuum_name()} reported an error."
        if details:
            message = f"{message} {details}"
        await self._async_notify(
            "error",
            "Vacuum needs help",
            message,
            self.options.get(CONF_ERROR_NOTIFY_SERVICE),
        )

    async def _async_notify_completion(self, started: datetime | None) -> None:
        if not self.is_enabled(CONF_COMPLETION_ENABLED):
            return
        details: list[str] = []
        area = self._statistic_text(
            self._find_device_entity(
                "sensor", ("current statistics area", "current_statistics_area")
            ),
            is_duration=False,
        )
        if area:
            details.append(area)
        duration = self._statistic_text(
            self._find_device_entity(
                "sensor", ("current statistics time", "current_statistics_time")
            ),
            is_duration=True,
        )
        if duration is None and started is not None:
            elapsed = (dt_util.utcnow() - started).total_seconds()
            duration = format_duration(elapsed)
        if duration:
            details.append(f"in {duration}")

        message = f"{self._vacuum_name()} finished cleaning"
        if details:
            message = f"{message} ({', '.join(details)})"
        await self._async_notify(
            "completion",
            "Cleaning finished",
            f"{message}.",
            self.options.get(CONF_COMPLETION_NOTIFY_SERVICE),
        )

    async def _async_notify(
        self,
        kind: str,
        title: str,
        message: str,
        service: Any = None,
    ) -> None:
        service_name = str(service or self.options.get(CONF_NOTIFY_SERVICE) or "")
        parsed = split_service(service_name)
        if parsed and self.hass.services.has_service(*parsed):
            try:
                await self.hass.services.async_call(
                    parsed[0],
                    parsed[1],
                    {"title": title, "message": message},
                    blocking=False,
                )
                return
            except HomeAssistantError as err:
                _LOGGER.warning("Could not send notification: %s", err)
        elif service_name:
            _LOGGER.warning(
                "Notification service %s is not available, using a persistent notification",
                service_name,
            )

        persistent_notification.async_create(
            self.hass,
            message,
            title,
            notification_id=f"{DOMAIN}_{self.entry.entry_id}_{kind}",
        )

    async def _async_post_run(self) -> None:
        if self.is_enabled(CONF_AUTO_EMPTY_ENABLED):
            entity_id = self.auto_empty_entity()
            if entity_id:
                await self._async_service("button", "press", {"entity_id": entity_id})

        service = str(self.options.get(CONF_POST_RUN_SERVICE) or "")
        parsed = split_service(service)
        if parsed is None:
            if service:
                _LOGGER.warning("Invalid post-run service: %s", service)
            return
        if not self.hass.services.has_service(*parsed):
            _LOGGER.warning("Post-run service %s is not available", service)
            return
        await self._async_service(*parsed, {})

    async def _async_abort(self, action: str, quiet: bool = False) -> None:
        if action not in ("return_to_base", "pause", "stop"):
            action = "return_to_base"
        if action == "pause":
            service = "pause"
            if quiet:
                self._paused_by_quiet = True
        elif action == "stop":
            service = "stop"
            if quiet:
                self._paused_by_quiet = False
            self._suppress_completion = True
        else:
            service = "return_to_base"
            if quiet:
                self._paused_by_quiet = False
            self._suppress_completion = True
        await self._async_service("vacuum", service, {"entity_id": self.vacuum_entity})

    async def _async_apply_fan_speed(self) -> None:
        speed = str(self.options.get(CONF_FAN_SPEED) or "no_change")
        if speed == "no_change":
            return
        entity_id = self.fan_entity()
        if not entity_id:
            return
        state = self.hass.states.get(entity_id)
        if state is None or speed not in state.attributes.get("options", []):
            _LOGGER.debug("Fan speed %s is not available on %s", speed, entity_id)
            return
        await self._async_service(
            "select", "select_option", {"entity_id": entity_id, "option": speed}
        )

    async def _async_service(self, domain: str, service: str, data: dict[str, Any]) -> None:
        try:
            await self.hass.services.async_call(domain, service, data, blocking=True)
        except HomeAssistantError as err:
            _LOGGER.warning("Could not call %s.%s: %s", domain, service, err)

    # ------------------------------------------------------------------
    # Entity discovery
    # ------------------------------------------------------------------

    def _lookup_device_id(self) -> str | None:
        registry = er.async_get(self.hass)
        entry = registry.async_get(self.vacuum_entity)
        return entry.device_id if entry else None

    def _vacuum_device_id(self) -> str | None:
        if self._device_id is None:
            self._device_id = self._lookup_device_id()
        return self._device_id

    def _device_entities(self, domain: str | None = None) -> list[er.RegistryEntry]:
        device_id = self._vacuum_device_id()
        if not device_id:
            return []
        registry = er.async_get(self.hass)
        return [
            entry
            for entry in er.async_entries_for_device(registry, device_id)
            if domain is None or entry.domain == domain
        ]

    def _find_device_entity(self, domain: str, keywords: tuple[str, ...]) -> str | None:
        for entry in self._device_entities(domain):
            state = self.hass.states.get(entry.entity_id)
            haystack = " ".join(
                filter(
                    None,
                    (
                        entry.entity_id,
                        entry.name,
                        entry.original_name,
                        state.name if state else None,
                    ),
                )
            ).lower()
            if any(keyword in haystack for keyword in keywords):
                return entry.entity_id
        return None

    def fan_entity(self) -> str | None:
        """Return the configured or auto-discovered fan select entity."""
        configured = str(self.options.get(CONF_FAN_ENTITY) or "")
        if configured:
            return configured
        return self._find_device_entity("select", ("fan",))

    def auto_empty_entity(self) -> str | None:
        """Return the configured or auto-discovered auto-empty button."""
        configured = str(self.options.get(CONF_AUTO_EMPTY_ENTITY) or "")
        if configured:
            return configured
        return self._find_device_entity("button", ("auto empty", "auto_empty", "empty dock"))

    def maintenance_entities(self) -> list[str]:
        """Return configured consumable sensors or auto-discover them."""
        configured = self.options.get(CONF_MAINTENANCE_SENSORS) or []
        if configured:
            return [entity for entity in configured if self.hass.states.get(entity)]

        entities: list[str] = []
        for entry in self._device_entities("sensor"):
            state = self.hass.states.get(entry.entity_id)
            if state is None:
                continue
            if state.attributes.get(ATTR_DEVICE_CLASS) == "battery":
                continue
            if state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) != "%":
                continue
            haystack = " ".join(
                filter(None, (entry.entity_id, entry.name, entry.original_name))
            ).lower()
            if any(keyword in haystack for keyword in CONSUMABLE_EXCLUDE_KEYWORDS):
                continue
            if parse_percentage(state.state) is None:
                continue
            entities.append(entry.entity_id)
        return entities

    def _vacuum_state(self) -> State | None:
        return self.hass.states.get(self.vacuum_entity)

    def _vacuum_name(self) -> str:
        state = self._vacuum_state()
        if state is not None:
            return state.name
        return "Robot vacuum"

    def _battery_level(self) -> Any:
        state = self._vacuum_state()
        if state is not None:
            for attribute in ("battery_level", "battery"):
                if attribute in state.attributes:
                    return state.attributes[attribute]

        for entry in self._device_entities("sensor"):
            sensor_state = self.hass.states.get(entry.entity_id)
            if sensor_state is None:
                continue
            haystack = " ".join(
                filter(None, (entry.entity_id, entry.name, entry.original_name))
            ).lower()
            if sensor_state.attributes.get(ATTR_DEVICE_CLASS) == "battery" or any(
                keyword in haystack for keyword in BATTERY_ENTITY_KEYWORDS
            ):
                return sensor_state.state
        return None

    def _entity_name(self, entity_id: str, state: State) -> str:
        registry = er.async_get(self.hass)
        entry = registry.async_get(entity_id)
        if entry is not None:
            return entry.name or entry.original_name or state.name
        return state.name

    def _statistic_text(self, entity_id: str | None, is_duration: bool) -> str | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None:
            return None
        try:
            value = float(state.state)
        except (TypeError, ValueError):
            return None
        if is_duration:
            unit = str(state.attributes.get(ATTR_UNIT_OF_MEASUREMENT) or "s").lower()
            if unit in ("min", "minute", "minutes"):
                value *= 60
            elif unit in ("h", "hour", "hours"):
                value *= 3600
            return format_duration(value)
        unit = state.attributes.get(ATTR_UNIT_OF_MEASUREMENT)
        return f"{format_number(value)} {unit}" if unit else format_number(value)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _register_time(
        self,
        option: str,
        action: Callable[[datetime], Any],
    ) -> None:
        parsed = parse_time(self.options.get(option))
        if parsed is None:
            return
        self._unsubs.append(
            async_track_time_change(
                self.hass,
                action,
                hour=parsed.hour,
                minute=parsed.minute,
                second=parsed.second,
            )
        )
