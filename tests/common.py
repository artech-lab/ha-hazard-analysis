"""Helpers shared by the tests."""

from __future__ import annotations

from typing import Any

from homeassistant.components.ai_task import AITaskEntityFeature
from homeassistant.core import HomeAssistant

ENGINE = "ai_task.vision"
FALLBACK = "ai_task.cloud"
CAMERAS = ["camera.area_north", "camera.area_south"]

SAFE: dict[str, Any] = {
    "fire": 0,
    "smoke": 0,
    "flood": 0,
    "accident": 0,
    "other": 0,
    "confidence": 9,
    "summary": "The area looks clear.",
    "recommendation": "No action needed",
}


def reading(**values: Any) -> dict[str, Any]:
    """A fake AI response: the safe one with some fields changed."""
    return {**SAFE, **values}


def add_engines(hass: HomeAssistant, *entity_ids: str) -> None:
    """Fake AI Task entities with image support."""
    features = AITaskEntityFeature.GENERATE_DATA | AITaskEntityFeature.SUPPORT_ATTACHMENTS
    for entity_id in entity_ids or (ENGINE,):
        hass.states.async_set(entity_id, "unknown", {"supported_features": int(features)})
