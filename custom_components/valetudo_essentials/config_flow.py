"""Config and options flow for Valetudo Essentials."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_AUTO_EMPTY_ENTITY,
    CONF_AWAY_DELAY,
    CONF_BATTERY_MIN,
    CONF_COMPLETION_NOTIFY_SERVICE,
    CONF_ERROR_NOTIFY_SERVICE,
    CONF_FAN_ENTITY,
    CONF_FAN_SPEED,
    CONF_HOME_ACTION,
    CONF_MAINTENANCE_SENSORS,
    CONF_MAINTENANCE_THRESHOLD,
    CONF_MAINTENANCE_TIME,
    CONF_NOTIFY_SERVICE,
    CONF_POST_RUN_SERVICE,
    CONF_PRESENCE_ENTITY,
    CONF_QUIET_ACTION,
    CONF_QUIET_END,
    CONF_QUIET_RESUME,
    CONF_QUIET_START,
    CONF_SCHEDULE_DAYS,
    CONF_SCHEDULE_ONLY_WHEN_AWAY,
    CONF_SCHEDULE_TIME,
    CONF_VACUUM_ENTITY,
    DEFAULT_BATTERY_MIN,
    DEFAULT_FAN_SPEED,
    DEFAULT_MAINTENANCE_THRESHOLD,
    DEFAULT_OPTIONS,
    DOMAIN,
    FAN_SPEEDS,
    WEEKDAY_LABELS,
    WEEKDAYS,
)
from .engine import merged_options
from .logic import parse_time, split_service

PRESENCE_DOMAINS = [
    "binary_sensor",
    "input_boolean",
    "person",
    "device_tracker",
    "zone",
]

ACTION_OPTIONS = [
    selector.SelectOptionDict(value="return_to_base", label="Return to the dock"),
    selector.SelectOptionDict(value="pause", label="Pause"),
    selector.SelectOptionDict(value="stop", label="Stop"),
]

FAN_OPTIONS = [
    selector.SelectOptionDict(value=speed, label=speed.replace("_", " ").title())
    for speed in FAN_SPEEDS
]

WEEKDAY_OPTIONS = [
    selector.SelectOptionDict(value=day, label=WEEKDAY_LABELS[day]) for day in WEEKDAYS
]


def _valid_service(value: str | None) -> bool:
    return not value or split_service(value) is not None


class ValetudoEssentialsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Add a Valetudo vacuum."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Pick the vacuum to manage."""
        errors: dict[str, str] = {}

        if user_input is not None:
            entity_id = user_input[CONF_VACUUM_ENTITY]
            if self.hass.states.get(entity_id) is None:
                errors["base"] = "entity_not_found"
            else:
                await self.async_set_unique_id(entity_id)
                self._abort_if_unique_id_configured()
                state = self.hass.states.get(entity_id)
                title = state.name if state is not None else entity_id
                return self.async_create_entry(title=title, data={CONF_VACUUM_ENTITY: entity_id})

        schema = vol.Schema(
            {
                vol.Required(CONF_VACUUM_ENTITY): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="vacuum")
                )
            }
        )
        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: Any) -> ValetudoEssentialsOptionsFlow:
        """Return the options flow."""
        return ValetudoEssentialsOptionsFlow()


class ValetudoEssentialsOptionsFlow(OptionsFlowWithReload):
    """Configure the built-in automations."""

    def __init__(self) -> None:
        self._options: dict[str, Any] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Show the settings menu."""
        if not self._options:
            self._options = merged_options(self.config_entry.options)
        return self.async_show_menu(
            step_id="init",
            menu_options=[
                "general",
                "away",
                "home",
                "quiet",
                "schedule",
                "notifications",
                "maintenance",
                "finish",
            ],
        )

    async def async_step_general(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure presence, battery, and shared services."""
        if user_input is not None:
            user_input.setdefault(CONF_FAN_ENTITY, "")
            user_input[CONF_NOTIFY_SERVICE] = str(user_input.get(CONF_NOTIFY_SERVICE) or "").strip()
            user_input[CONF_POST_RUN_SERVICE] = str(
                user_input.get(CONF_POST_RUN_SERVICE) or ""
            ).strip()
            errors: dict[str, str] = {}
            if not _valid_service(user_input[CONF_NOTIFY_SERVICE]):
                errors["base"] = "invalid_service"
            elif not _valid_service(user_input[CONF_POST_RUN_SERVICE]):
                errors["base"] = "invalid_service"
            if errors:
                return self.async_show_form(
                    step_id="general",
                    data_schema=self._general_schema(user_input),
                    errors=errors,
                )
            self._options.update(user_input)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="general",
            data_schema=self._general_schema(self._options),
        )

    async def async_step_away(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure the clean-when-away automation."""
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="away",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_AWAY_DELAY,
                        default=int(self._options[CONF_AWAY_DELAY]),
                    ): selector.NumberSelector(
                        selector.NumberSelectorConfig(
                            min=0,
                            max=240,
                            step=1,
                            unit_of_measurement="min",
                            mode=selector.NumberSelectorMode.BOX,
                        )
                    )
                }
            ),
        )

    async def async_step_home(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure the come-home automation."""
        if user_input is not None:
            self._options.update(user_input)
            return await self.async_step_init()

        action = self._options[CONF_HOME_ACTION]
        return self.async_show_form(
            step_id="home",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_HOME_ACTION, default=action): selector.SelectSelector(
                        selector.SelectSelectorConfig(options=ACTION_OPTIONS)
                    )
                }
            ),
        )

    async def async_step_quiet(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Configure quiet hours."""
        if user_input is not None:
            start = parse_time(user_input.get(CONF_QUIET_START))
            end = parse_time(user_input.get(CONF_QUIET_END))
            if start is None or end is None:
                return self.async_show_form(
                    step_id="quiet",
                    data_schema=self._quiet_schema(user_input),
                    errors={"base": "invalid_time"},
                )
            if start == end:
                return self.async_show_form(
                    step_id="quiet",
                    data_schema=self._quiet_schema(user_input),
                    errors={"base": "same_times"},
                )
            self._options.update(user_input)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="quiet",
            data_schema=self._quiet_schema(self._options),
        )

    async def async_step_schedule(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure the weekly schedule."""
        if user_input is not None:
            days = user_input.get(CONF_SCHEDULE_DAYS) or []
            if not days:
                return self.async_show_form(
                    step_id="schedule",
                    data_schema=self._schedule_schema(user_input),
                    errors={"base": "no_days"},
                )
            if parse_time(user_input.get(CONF_SCHEDULE_TIME)) is None:
                return self.async_show_form(
                    step_id="schedule",
                    data_schema=self._schedule_schema(user_input),
                    errors={"base": "invalid_time"},
                )
            self._options.update(user_input)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="schedule",
            data_schema=self._schedule_schema(self._options),
        )

    async def async_step_notifications(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure notification services."""
        if user_input is not None:
            user_input[CONF_ERROR_NOTIFY_SERVICE] = str(
                user_input.get(CONF_ERROR_NOTIFY_SERVICE) or ""
            ).strip()
            user_input[CONF_COMPLETION_NOTIFY_SERVICE] = str(
                user_input.get(CONF_COMPLETION_NOTIFY_SERVICE) or ""
            ).strip()
            errors: dict[str, str] = {}
            if not _valid_service(user_input[CONF_ERROR_NOTIFY_SERVICE]):
                errors["base"] = "invalid_service"
            elif not _valid_service(user_input[CONF_COMPLETION_NOTIFY_SERVICE]):
                errors["base"] = "invalid_service"
            if errors:
                return self.async_show_form(
                    step_id="notifications",
                    data_schema=self._notification_schema(user_input),
                    errors=errors,
                )
            self._options.update(user_input)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="notifications",
            data_schema=self._notification_schema(self._options),
        )

    async def async_step_maintenance(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Configure consumable and dock supply reminders."""
        if user_input is not None:
            user_input.setdefault(CONF_MAINTENANCE_SENSORS, [])
            if parse_time(user_input.get(CONF_MAINTENANCE_TIME)) is None:
                return self.async_show_form(
                    step_id="maintenance",
                    data_schema=self._maintenance_schema(user_input),
                    errors={"base": "invalid_time"},
                )
            self._options.update(user_input)
            return await self.async_step_init()

        return self.async_show_form(
            step_id="maintenance",
            data_schema=self._maintenance_schema(self._options),
        )

    async def async_step_finish(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Save all settings."""
        return self.async_create_entry(title="", data=self._options)

    # ------------------------------------------------------------------
    # Schemas
    # ------------------------------------------------------------------

    def _general_schema(self, values: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional(
                    CONF_PRESENCE_ENTITY,
                    default=str(
                        values.get(
                            CONF_PRESENCE_ENTITY,
                            DEFAULT_OPTIONS[CONF_PRESENCE_ENTITY],
                        )
                    ),
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain=PRESENCE_DOMAINS)),
                vol.Optional(
                    CONF_BATTERY_MIN,
                    default=float(values.get(CONF_BATTERY_MIN, DEFAULT_BATTERY_MIN)),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(
                    CONF_FAN_ENTITY,
                    description={"suggested_value": values.get(CONF_FAN_ENTITY) or None},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="select")),
                vol.Optional(
                    CONF_FAN_SPEED,
                    default=str(values.get(CONF_FAN_SPEED, DEFAULT_FAN_SPEED)),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(options=FAN_OPTIONS, custom_value=True)
                ),
                vol.Optional(
                    CONF_NOTIFY_SERVICE,
                    default=str(values.get(CONF_NOTIFY_SERVICE) or ""),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_POST_RUN_SERVICE,
                    default=str(values.get(CONF_POST_RUN_SERVICE) or ""),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_AUTO_EMPTY_ENTITY,
                    description={"suggested_value": values.get(CONF_AUTO_EMPTY_ENTITY) or None},
                ): selector.EntitySelector(selector.EntitySelectorConfig(domain="button")),
            }
        )

    def _quiet_schema(self, values: dict[str, Any]) -> vol.Schema:
        start = parse_time(values.get(CONF_QUIET_START))
        end = parse_time(values.get(CONF_QUIET_END))
        schema: dict[Any, Any] = {
            vol.Optional(
                CONF_QUIET_RESUME,
                default=bool(values.get(CONF_QUIET_RESUME, True)),
            ): selector.BooleanSelector(),
            vol.Optional(
                CONF_QUIET_ACTION,
                default=str(values.get(CONF_QUIET_ACTION, "pause")),
            ): selector.SelectSelector(selector.SelectSelectorConfig(options=ACTION_OPTIONS)),
        }
        if start is not None:
            schema[vol.Optional(CONF_QUIET_START, default=start)] = selector.TimeSelector()
        else:
            schema[vol.Required(CONF_QUIET_START)] = selector.TimeSelector()
        if end is not None:
            schema[vol.Optional(CONF_QUIET_END, default=end)] = selector.TimeSelector()
        else:
            schema[vol.Required(CONF_QUIET_END)] = selector.TimeSelector()
        return vol.Schema(schema)

    def _schedule_schema(self, values: dict[str, Any]) -> vol.Schema:
        schedule_time = parse_time(values.get(CONF_SCHEDULE_TIME))
        time_field: Any
        if schedule_time is not None:
            time_field = vol.Optional(CONF_SCHEDULE_TIME, default=schedule_time)
        else:
            time_field = vol.Required(CONF_SCHEDULE_TIME)
        return vol.Schema(
            {
                vol.Optional(
                    CONF_SCHEDULE_DAYS,
                    default=list(
                        values.get(CONF_SCHEDULE_DAYS, DEFAULT_OPTIONS[CONF_SCHEDULE_DAYS])
                    ),
                ): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=WEEKDAY_OPTIONS,
                        multiple=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                time_field: selector.TimeSelector(),
                vol.Optional(
                    CONF_SCHEDULE_ONLY_WHEN_AWAY,
                    default=bool(values.get(CONF_SCHEDULE_ONLY_WHEN_AWAY, False)),
                ): selector.BooleanSelector(),
            }
        )

    def _notification_schema(self, values: dict[str, Any]) -> vol.Schema:
        return vol.Schema(
            {
                vol.Optional(
                    CONF_ERROR_NOTIFY_SERVICE,
                    default=str(values.get(CONF_ERROR_NOTIFY_SERVICE) or ""),
                ): selector.TextSelector(),
                vol.Optional(
                    CONF_COMPLETION_NOTIFY_SERVICE,
                    default=str(values.get(CONF_COMPLETION_NOTIFY_SERVICE) or ""),
                ): selector.TextSelector(),
            }
        )

    def _maintenance_schema(self, values: dict[str, Any]) -> vol.Schema:
        sensors = values.get(CONF_MAINTENANCE_SENSORS) or None
        maintenance_time = parse_time(values.get(CONF_MAINTENANCE_TIME))
        time_field: Any
        if maintenance_time is not None:
            time_field = vol.Optional(CONF_MAINTENANCE_TIME, default=maintenance_time)
        else:
            time_field = vol.Required(CONF_MAINTENANCE_TIME)
        return vol.Schema(
            {
                vol.Optional(
                    CONF_MAINTENANCE_SENSORS,
                    description={"suggested_value": sensors},
                ): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain="sensor", multiple=True)
                ),
                vol.Optional(
                    CONF_MAINTENANCE_THRESHOLD,
                    default=float(
                        values.get(
                            CONF_MAINTENANCE_THRESHOLD,
                            DEFAULT_MAINTENANCE_THRESHOLD,
                        )
                    ),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=0,
                        max=100,
                        step=1,
                        unit_of_measurement="%",
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                time_field: selector.TimeSelector(),
            }
        )
