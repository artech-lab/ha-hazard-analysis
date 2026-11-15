# SPDX-License-Identifier: GPL-3.0-or-later
"""Sensors for Hazard Analysis."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import EntityCategory, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import HazardConfigEntry
from .const import HAZARDS, LEVELS, MAX_CONFIDENCE
from .entity import HazardEntity
from .monitor import HazardMonitor


@dataclass(frozen=True, kw_only=True)
class HazardSensorDescription(SensorEntityDescription):
    """Describes a Hazard Analysis sensor."""

    value_fn: Callable[[HazardMonitor], Any]
    attributes_fn: Callable[[HazardMonitor], dict[str, Any] | None] = lambda _: None


def _level(key: str) -> Callable[[HazardMonitor], Any]:
    return lambda m: m.levels[key]


SENSORS: tuple[HazardSensorDescription, ...] = (
    HazardSensorDescription(
        key="risk_level",
        device_class=SensorDeviceClass.ENUM,
        options=list(LEVELS),
        value_fn=lambda m: m.risk_level,
        attributes_fn=lambda m: {"level": m.max_level, "levels": dict(m.levels)},
    ),
    *(
        HazardSensorDescription(
            key=key,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            value_fn=_level(key),
        )
        for key in HAZARDS
    ),
    HazardSensorDescription(
        key="confidence",
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=lambda m: m.confidence,
        attributes_fn=lambda _: {"max": MAX_CONFIDENCE},
    ),
    HazardSensorDescription(key="summary", value_fn=lambda m: m.summary),
    HazardSensorDescription(
        key="recommendation",
        value_fn=lambda m: m.recommendation,
        attributes_fn=lambda m: {"action_required": m.action_required},
    ),
    HazardSensorDescription(
        key="last_analysis",
        device_class=SensorDeviceClass.TIMESTAMP,
        value_fn=lambda m: m.last_analysis,
    ),
    HazardSensorDescription(
        key="analysis_duration",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        suggested_display_precision=1,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda m: m.last_duration,
    ),
    HazardSensorDescription(
        key="ai_engine",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda m: m.last_engine,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: HazardConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    async_add_entities(HazardSensor(entry.runtime_data, description, "sensor") for description in SENSORS)


class HazardSensor(HazardEntity, SensorEntity):
    """A Hazard Analysis sensor."""

    entity_description: HazardSensorDescription

    @property
    def native_value(self) -> Any:
        """Current value."""
        return self.entity_description.value_fn(self.monitor)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        """Extra attributes of some sensors."""
        return self.entity_description.attributes_fn(self.monitor)
