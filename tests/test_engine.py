"""Behavioral tests for the automation engine."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.valetudo_essentials.const import (
    CONF_AUTO_EMPTY_ENABLED,
    CONF_AUTO_EMPTY_ENTITY,
    CONF_AWAY_DELAY,
    CONF_AWAY_ENABLED,
    CONF_BATTERY_MIN,
    CONF_COMPLETION_ENABLED,
    CONF_HOME_ACTION,
    CONF_HOME_ENABLED,
    CONF_MAINTENANCE_SENSORS,
    CONF_MAINTENANCE_THRESHOLD,
    CONF_NOTIFY_SERVICE,
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
    DOMAIN,
    WEEKDAYS,
)


async def _setup_entry(hass: HomeAssistant, options: dict | None = None) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Roomba",
        data={CONF_VACUUM_ENTITY: "vacuum.roomba"},
        options=options or {},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def test_clean_when_away_starts_vacuum(hass: HomeAssistant, enable_custom_integrations):
    calls: list[ServiceCall] = []

    async def start_handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("vacuum", "start", start_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("zone.home", "1")

    await _setup_entry(
        hass,
        {
            CONF_AWAY_DELAY: 0,
            CONF_QUIET_ENABLED: False,
            CONF_HOME_ENABLED: False,
        },
    )

    hass.states.async_set("zone.home", "0")
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "vacuum.roomba"


async def test_clean_when_away_respects_battery(hass: HomeAssistant, enable_custom_integrations):
    calls: list[ServiceCall] = []

    async def start_handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("vacuum", "start", start_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 10})
    hass.states.async_set("zone.home", "1")

    await _setup_entry(
        hass,
        {
            CONF_AWAY_DELAY: 0,
            CONF_QUIET_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_BATTERY_MIN: 20,
        },
    )

    hass.states.async_set("zone.home", "0")
    await hass.async_block_till_done()

    assert calls == []


async def test_arriving_home_docks_vacuum(hass: HomeAssistant, enable_custom_integrations):
    calls: list[ServiceCall] = []

    async def home_handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("vacuum", "return_to_base", home_handler)
    hass.states.async_set("vacuum.roomba", "cleaning", {"battery_level": 80})
    hass.states.async_set("zone.home", "0")

    await _setup_entry(
        hass,
        {
            CONF_AWAY_DELAY: 0,
            CONF_QUIET_ENABLED: False,
            CONF_HOME_ENABLED: True,
            CONF_HOME_ACTION: "return_to_base",
            CONF_PRESENCE_ENTITY: "zone.home",
        },
    )

    hass.states.async_set("zone.home", "1")
    await hass.async_block_till_done()

    assert len(calls) == 1
    assert calls[0].data["entity_id"] == "vacuum.roomba"


async def test_disabled_away_automation_does_nothing(
    hass: HomeAssistant, enable_custom_integrations
):
    calls: list[ServiceCall] = []

    async def start_handler(call: ServiceCall) -> None:
        calls.append(call)

    hass.services.async_register("vacuum", "start", start_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("zone.home", "1")

    await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_AWAY_DELAY: 0,
            CONF_QUIET_ENABLED: False,
            CONF_HOME_ENABLED: False,
        },
    )

    hass.states.async_set("zone.home", "0")
    await hass.async_block_till_done()

    assert calls == []


async def test_quiet_hours_pause_and_resume(hass: HomeAssistant, enable_custom_integrations):
    paused: list[ServiceCall] = []
    started: list[ServiceCall] = []

    async def pause_handler(call: ServiceCall) -> None:
        paused.append(call)

    async def start_handler(call: ServiceCall) -> None:
        started.append(call)

    hass.services.async_register("vacuum", "pause", pause_handler)
    hass.services.async_register("vacuum", "start", start_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("zone.home", "1")

    now = dt_util.now()
    window_start = (now - timedelta(hours=1)).strftime("%H:%M:%S")
    window_end = (now + timedelta(hours=1)).strftime("%H:%M:%S")
    entry = await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_QUIET_ENABLED: True,
            CONF_QUIET_START: window_start,
            CONF_QUIET_END: window_end,
            CONF_QUIET_ACTION: "pause",
            CONF_QUIET_RESUME: True,
        },
    )

    hass.states.async_set("vacuum.roomba", "cleaning")
    await hass.async_block_till_done()

    assert len(paused) == 1
    assert entry.runtime_data._paused_by_quiet is True

    hass.states.async_set("vacuum.roomba", "paused")
    await hass.async_block_till_done()

    # Move the configured window away from the current time so the end handler
    # treats this as the end of quiet hours.
    entry.runtime_data.options[CONF_QUIET_START] = (now + timedelta(hours=2)).strftime("%H:%M:%S")
    entry.runtime_data.options[CONF_QUIET_END] = (now + timedelta(hours=3)).strftime("%H:%M:%S")
    await entry.runtime_data._async_quiet_end(now)
    await hass.async_block_till_done()

    assert len(started) == 1
    assert entry.runtime_data._paused_by_quiet is False


async def test_completion_notification_and_auto_empty(
    hass: HomeAssistant, enable_custom_integrations
):
    notifications: list[ServiceCall] = []
    pressed: list[ServiceCall] = []

    async def notify_handler(call: ServiceCall) -> None:
        notifications.append(call)

    async def press_handler(call: ServiceCall) -> None:
        pressed.append(call)

    hass.services.async_register("notify", "test", notify_handler)
    hass.services.async_register("button", "press", press_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("button.empty", "unknown")
    hass.states.async_set("zone.home", "1")

    await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_QUIET_ENABLED: False,
            CONF_NOTIFY_SERVICE: "notify.test",
            CONF_COMPLETION_ENABLED: True,
            CONF_AUTO_EMPTY_ENABLED: True,
            CONF_AUTO_EMPTY_ENTITY: "button.empty",
        },
    )

    hass.states.async_set("vacuum.roomba", "cleaning")
    await hass.async_block_till_done()
    hass.states.async_set("vacuum.roomba", "docked")
    await hass.async_block_till_done()

    assert len(pressed) == 1
    assert pressed[0].data["entity_id"] == "button.empty"
    assert len(notifications) == 1
    assert "finished cleaning" in notifications[0].data["message"]


async def test_error_notification(hass: HomeAssistant, enable_custom_integrations):
    notifications: list[ServiceCall] = []

    async def notify_handler(call: ServiceCall) -> None:
        notifications.append(call)

    hass.services.async_register("notify", "test", notify_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("zone.home", "1")

    await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_QUIET_ENABLED: False,
            CONF_NOTIFY_SERVICE: "notify.test",
        },
    )

    hass.states.async_set("vacuum.roomba", "error", {"error_description": "Bumper stuck"})
    await hass.async_block_till_done()

    assert len(notifications) == 1
    assert "Bumper stuck" in notifications[0].data["message"]


async def test_maintenance_reminder(hass: HomeAssistant, enable_custom_integrations):
    notifications: list[ServiceCall] = []

    async def notify_handler(call: ServiceCall) -> None:
        notifications.append(call)

    hass.services.async_register("notify", "test", notify_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("sensor.main_brush", "5", {"friendly_name": "Main brush"})
    hass.states.async_set("sensor.filter", "55", {"friendly_name": "Filter"})
    hass.states.async_set("zone.home", "1")

    entry = await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_QUIET_ENABLED: False,
            CONF_NOTIFY_SERVICE: "notify.test",
            CONF_MAINTENANCE_SENSORS: ["sensor.main_brush", "sensor.filter"],
            CONF_MAINTENANCE_THRESHOLD: 10,
        },
    )

    await entry.runtime_data._async_maintenance(dt_util.now())
    await hass.async_block_till_done()

    assert len(notifications) == 1
    assert "Main brush: 5%" in notifications[0].data["message"]
    assert "Filter" not in notifications[0].data["message"]


async def test_schedule_starts_on_selected_day(hass: HomeAssistant, enable_custom_integrations):
    started: list[ServiceCall] = []

    async def start_handler(call: ServiceCall) -> None:
        started.append(call)

    hass.services.async_register("vacuum", "start", start_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("zone.home", "1")

    now = dt_util.now()
    entry = await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_QUIET_ENABLED: False,
            CONF_SCHEDULE_ENABLED: True,
            CONF_SCHEDULE_DAYS: [WEEKDAYS[now.weekday()]],
            CONF_SCHEDULE_TIME: "09:00:00",
            CONF_SCHEDULE_ONLY_WHEN_AWAY: False,
        },
    )

    await entry.runtime_data._async_schedule(now)
    await hass.async_block_till_done()

    assert len(started) == 1


async def test_schedule_respects_only_when_away(hass: HomeAssistant, enable_custom_integrations):
    started: list[ServiceCall] = []

    async def start_handler(call: ServiceCall) -> None:
        started.append(call)

    hass.services.async_register("vacuum", "start", start_handler)
    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set("zone.home", "1")

    now = dt_util.now()
    entry = await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_QUIET_ENABLED: False,
            CONF_SCHEDULE_ENABLED: True,
            CONF_SCHEDULE_DAYS: [WEEKDAYS[now.weekday()]],
            CONF_SCHEDULE_TIME: "09:00:00",
            CONF_SCHEDULE_ONLY_WHEN_AWAY: True,
        },
    )

    await entry.runtime_data._async_schedule(now)
    await hass.async_block_till_done()

    assert started == []


async def test_device_entity_discovery(hass: HomeAssistant, enable_custom_integrations):
    entry = await _setup_entry(
        hass,
        {
            CONF_AWAY_ENABLED: False,
            CONF_HOME_ENABLED: False,
            CONF_QUIET_ENABLED: False,
        },
    )

    device_registry = dr.async_get(hass)
    entity_registry = er.async_get(hass)
    device = device_registry.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={("mqtt", "roomba-123")},
        name="Roomba",
    )
    entity_registry.async_get_or_create(
        "vacuum",
        "mqtt",
        "roomba-123",
        device_id=device.id,
        suggested_object_id="roomba",
    )
    main_brush = entity_registry.async_get_or_create(
        "sensor",
        "mqtt",
        "main-brush",
        device_id=device.id,
        original_name="Main brush",
        suggested_object_id="main_brush",
    )
    battery = entity_registry.async_get_or_create(
        "sensor",
        "mqtt",
        "battery",
        device_id=device.id,
        original_name="Battery",
        suggested_object_id="battery",
    )
    button = entity_registry.async_get_or_create(
        "button",
        "mqtt",
        "auto-empty",
        device_id=device.id,
        original_name="Trigger Auto Empty Dock",
        suggested_object_id="trigger_auto_empty_dock",
    )
    fan = entity_registry.async_get_or_create(
        "select",
        "mqtt",
        "fan",
        device_id=device.id,
        original_name="Fan",
        suggested_object_id="fan",
    )

    hass.states.async_set("vacuum.roomba", "docked", {"battery_level": 90})
    hass.states.async_set(main_brush.entity_id, "8", {"unit_of_measurement": "%"})
    hass.states.async_set(
        battery.entity_id,
        "90",
        {"unit_of_measurement": "%", "device_class": "battery"},
    )
    hass.states.async_set(button.entity_id, "unknown")
    hass.states.async_set(fan.entity_id, "medium", {"options": ["off", "medium", "max"]})

    engine = entry.runtime_data
    assert engine.maintenance_entities() == [main_brush.entity_id]
    assert engine.auto_empty_entity() == button.entity_id
    assert engine.fan_entity() == fan.entity_id
