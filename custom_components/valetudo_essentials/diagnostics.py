"""Diagnostics support for Valetudo Essentials."""

from __future__ import annotations

from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import AUTOMATIONS
from .engine import ValetudoEssentialsEngine


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostic information about one configured vacuum."""
    engine: ValetudoEssentialsEngine = entry.runtime_data
    vacuum = hass.states.get(engine.vacuum_entity)
    return {
        "vacuum_entity": engine.vacuum_entity,
        "presence_entity": engine.presence_entity,
        "vacuum_state": vacuum.state if vacuum is not None else None,
        "options": dict(engine.options),
        "enabled": {
            automation.key: engine.is_enabled(automation.key) for automation in AUTOMATIONS
        },
        "discovered": {
            "fan_entity": engine.fan_entity(),
            "auto_empty_entity": engine.auto_empty_entity(),
            "maintenance_entities": engine.maintenance_entities(),
        },
    }
