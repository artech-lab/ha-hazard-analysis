# SPDX-License-Identifier: GPL-3.0-or-later
"""Switch that pauses the automatic analyses."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HazardConfigEntry
from .entity import HazardEntity

SWITCH = SwitchEntityDescription(key="monitoring", entity_category=EntityCategory.CONFIG)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HazardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switch."""
    async_add_entities([HazardMonitoringSwitch(entry.runtime_data, SWITCH, "switch")])


class HazardMonitoringSwitch(HazardEntity, SwitchEntity):
    """Automatic analyses on (the button works either way)."""

    @property
    def is_on(self) -> bool:
        """Monitoring enabled."""
        return self.monitor.monitoring

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Resume."""
        await self.monitor.async_set_monitoring(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Pause."""
        await self.monitor.async_set_monitoring(False)
