"""Switches that enable or disable each built-in automation."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import AUTOMATIONS, CONF_AUTO_EMPTY_ENABLED, Automation
from .engine import ValetudoEssentialsEngine


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create one switch per built-in automation."""
    engine: ValetudoEssentialsEngine = entry.runtime_data
    async_add_entities(ValetudoAutomationSwitch(engine, automation) for automation in AUTOMATIONS)


class ValetudoAutomationSwitch(SwitchEntity):
    """Runtime toggle for a built-in automation."""

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self,
        engine: ValetudoEssentialsEngine,
        automation: Automation,
    ) -> None:
        self._engine = engine
        self._automation = automation
        self._attr_translation_key = automation.translation_key
        self._attr_unique_id = f"{engine.entry.entry_id}_{automation.key}"
        self._attr_icon = automation.icon

    @property
    def device_info(self) -> DeviceInfo:
        """Return the helper device."""
        return self._engine.device_info

    @property
    def available(self) -> bool:
        """Return whether the automation can run."""
        if self._automation.key == CONF_AUTO_EMPTY_ENABLED:
            entity_id = self._engine.auto_empty_entity()
            return entity_id is not None and self.hass.states.get(entity_id) is not None
        return self.hass.states.get(self._engine.vacuum_entity) is not None

    @property
    def is_on(self) -> bool:
        """Return whether the automation is enabled."""
        return self._engine.is_enabled(self._automation.key)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Expose the automation description."""
        return {"description": self._automation.description}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable the automation."""
        self._engine.set_enabled(self._automation.key, True)
        self.async_write_ha_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable the automation."""
        self._engine.set_enabled(self._automation.key, False)
        self.async_write_ha_state()
