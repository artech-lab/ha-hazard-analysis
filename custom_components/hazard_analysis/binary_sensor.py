# SPDX-License-Identifier: GPL-3.0-or-later
"""Binary sensors for Hazard Analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HazardConfigEntry
from .const import ALERT_LEVEL
from .entity import HazardEntity
from .monitor import HazardMonitor


@dataclass(frozen=True, kw_only=True)
class HazardBinaryDescription(BinarySensorEntityDescription):
    """Describes a Hazard Analysis binary sensor."""

    is_on_fn: Callable[[HazardMonitor], bool | None]
    attributes_fn: Callable[[HazardMonitor], dict[str, Any] | None] = lambda _: None


BINARY_SENSORS: tuple[HazardBinaryDescription, ...] = (
    HazardBinaryDescription(
        key="hazard",
        device_class=BinarySensorDeviceClass.SAFETY,
        is_on_fn=lambda m: None if m.risk_level is None else m.max_level >= ALERT_LEVEL,
    ),
    HazardBinaryDescription(
        key="analyzing",
        device_class=BinarySensorDeviceClass.RUNNING,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda m: m.running,
    ),
    HazardBinaryDescription(
        key="deescalation_pending",
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda m: m.deescalation_pending,
    ),
    HazardBinaryDescription(
        key="problem",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
        is_on_fn=lambda m: m.stale or m.last_error is not None,
        attributes_fn=lambda m: {
            "last_error": m.last_error,
            "last_attempt": m.last_attempt.isoformat() if m.last_attempt else None,
        },
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HazardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities(
        HazardBinarySensor(entry.runtime_data, description, "binary_sensor") for description in BINARY_SENSORS
    )


class HazardBinarySensor(HazardEntity, BinarySensorEntity):
    """A Hazard Analysis binary sensor."""

    entity_description: HazardBinaryDescription

    @property
    def is_on(self) -> bool | None:
        """Current value."""
        return self.entity_description.is_on_fn(self.monitor)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra attributes of the problem sensor."""
        return self.entity_description.attributes_fn(self.monitor)
