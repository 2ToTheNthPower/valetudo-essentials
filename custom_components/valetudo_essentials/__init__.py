"""Set up Valetudo Essentials."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_VACUUM_ENTITY
from .engine import ValetudoEssentialsEngine

PLATFORMS: list[Platform] = [Platform.SWITCH]


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up one Valetudo vacuum's automation helpers."""
    if CONF_VACUUM_ENTITY not in entry.data:
        return False

    engine = ValetudoEssentialsEngine(hass, entry)
    await engine.async_setup()
    entry.runtime_data = engine

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_unload()
    return unload_ok
