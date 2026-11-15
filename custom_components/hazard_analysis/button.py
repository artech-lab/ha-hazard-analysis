# SPDX-License-Identifier: GPL-3.0-or-later
"""Button that starts an analysis right away."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HazardConfigEntry
from .entity import HazardEntity

BUTTON = ButtonEntityDescription(key="analyze_now")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HazardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the button."""
    async_add_entities([HazardAnalyzeButton(entry.runtime_data, BUTTON, "button")])


class HazardAnalyzeButton(HazardEntity, ButtonEntity):
    """Run an analysis now (ignored while one is already running)."""

    async def async_press(self) -> None:
        """Start the analysis in the background, so the press returns at once."""
        if not self.monitor.running:
            self.monitor.schedule("manual")

    @property
    def available(self) -> bool:
        """Not pressable while an analysis is running."""
        return not self.monitor.running
