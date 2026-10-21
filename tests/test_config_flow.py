"""Config and options flow tests."""

from __future__ import annotations

from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.valetudo_essentials.const import (
    CONF_AWAY_DELAY,
    CONF_AWAY_ENABLED,
    CONF_QUIET_END,
    CONF_QUIET_START,
    CONF_VACUUM_ENTITY,
    DOMAIN,
)


async def test_user_flow_creates_entry(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("vacuum.roomba", "docked", {"friendly_name": "Downstairs Roomba"})

    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VACUUM_ENTITY: "vacuum.roomba"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Downstairs Roomba"
    assert result["data"] == {CONF_VACUUM_ENTITY: "vacuum.roomba"}

    await hass.async_block_till_done()
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert entry.state.name == "LOADED"


async def test_user_flow_rejects_duplicate(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("vacuum.roomba", "docked")
    first = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    await hass.config_entries.flow.async_configure(
        first["flow_id"], {CONF_VACUUM_ENTITY: "vacuum.roomba"}
    )
    await hass.async_block_till_done()

    second = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        second["flow_id"], {CONF_VACUUM_ENTITY: "vacuum.roomba"}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_user_flow_rejects_unknown_entity(hass: HomeAssistant, enable_custom_integrations):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_VACUUM_ENTITY: "vacuum.missing"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "entity_not_found"


async def test_options_flow_saves_settings(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("vacuum.roomba", "docked", {"friendly_name": "Roomba"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Roomba",
        data={CONF_VACUUM_ENTITY: "vacuum.roomba"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "away"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "away"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_AWAY_DELAY: 15}
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "quiet"}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "quiet_start": "07:00:00",
            "quiet_end": "07:00:00",
            "quiet_action": "pause",
            "quiet_resume": True,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "same_times"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "quiet_start": "23:30:00",
            "quiet_end": "06:30:00",
            "quiet_action": "return_to_base",
            "quiet_resume": False,
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options[CONF_AWAY_DELAY] == 15
    assert entry.options[CONF_QUIET_START] == "23:30:00"
    assert entry.options[CONF_QUIET_END] == "06:30:00"
    assert entry.state.name == "LOADED"


async def test_switches_persist_enabled_state(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("vacuum.roomba", "docked", {"friendly_name": "Roomba"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Roomba",
        data={CONF_VACUUM_ENTITY: "vacuum.roomba"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    switch_entities = [
        entity_id
        for entity_id in hass.states.async_entity_ids("switch")
        if "valetudo_essentials" in entity_id and "clean_when_away" in entity_id
    ]
    assert len(switch_entities) == 1
    entity_id = switch_entities[0]
    assert hass.states.get(entity_id).state == "on"

    await hass.services.async_call("switch", "turn_off", {"entity_id": entity_id}, blocking=True)
    await hass.async_block_till_done()

    assert hass.states.get(entity_id).state == "off"
    assert entry.options[CONF_AWAY_ENABLED] is False


async def test_options_flow_covers_every_section(hass: HomeAssistant, enable_custom_integrations):
    hass.states.async_set("vacuum.roomba", "docked", {"friendly_name": "Roomba"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Roomba",
        data={CONF_VACUUM_ENTITY: "vacuum.roomba"},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "general"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "presence_entity": "zone.home",
            "battery_min": 25,
            "fan_speed": "balanced",
            "notify_service": "notify.test",
            "post_run_service": "script.after_vacuum",
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "home"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"home_action": "pause"}
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "schedule"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "schedule_days": ["mon", "wed"],
            "schedule_time": "08:15:00",
            "schedule_only_when_away": True,
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "notifications"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "error_notify_service": "notify.errors",
            "completion_notify_service": "notify.done",
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "maintenance"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "maintenance_sensors": ["sensor.main_brush"],
            "maintenance_threshold": 15,
            "maintenance_time": "19:30:00",
        },
    )
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "finish"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert entry.options["battery_min"] == 25
    assert entry.options["presence_entity"] == "zone.home"
    assert entry.options["home_action"] == "pause"
    assert entry.options["schedule_days"] == ["mon", "wed"]
    assert entry.options["schedule_time"] == "08:15:00"
    assert entry.options["schedule_only_when_away"] is True
    assert entry.options["error_notify_service"] == "notify.errors"
    assert entry.options["maintenance_threshold"] == 15
    assert entry.options["maintenance_sensors"] == ["sensor.main_brush"]
    assert entry.options["maintenance_time"] == "19:30:00"
    assert entry.state.name == "LOADED"
