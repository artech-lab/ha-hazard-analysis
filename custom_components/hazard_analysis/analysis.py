# SPDX-License-Identifier: GPL-3.0-or-later
"""Pure functions of the hazard analysis: no Home Assistant imports.

AI response -> validated, clamped reading -> hysteresis -> stored levels
stored levels + context -> minutes until the next analysis
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import math
from typing import Any

from .const import (
    CADENCE_ACTIVE,
    CADENCE_IDLE,
    HAZARDS,
    LEVELS,
    MAX_CONFIDENCE,
    MAX_LEVEL,
    MAX_TEXT,
    RETRY_MIN,
)


class InvalidResponse(ValueError):
    """The AI response is missing a field or a field is not numeric."""


@dataclass(frozen=True, slots=True)
class Reading:
    """One validated analysis."""

    levels: dict[str, int]
    confidence: int
    summary: str
    recommendation: str
    action_required: bool

    @property
    def max_level(self) -> int:
        """Highest level among the categories."""
        return max(self.levels.values(), default=0)


def _number(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, bool):
        raise InvalidResponse(key)
    try:
        number = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        raise InvalidResponse(key) from None
    if not math.isfinite(number):
        raise InvalidResponse(key)
    return number


def _clamp(value: float, high: int) -> int:
    return max(0, min(high, round(value)))


def _text(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text if len(text) <= MAX_TEXT else text[: MAX_TEXT - 1].rstrip() + "…"


def parse_reading(data: Any, no_action: str) -> Reading:
    """Validate an AI response.

    Out-of-range numbers are clamped (a 7 becomes 4: fail-safe towards an
    alarm). A missing or non-numeric field raises ``InvalidResponse`` and the
    stored values stay untouched.
    """
    if not isinstance(data, Mapping):
        raise InvalidResponse("data")
    levels = {key: _clamp(_number(data, key), MAX_LEVEL) for key in HAZARDS}
    confidence = _clamp(_number(data, "confidence"), MAX_CONFIDENCE)
    recommendation = _text(data.get("recommendation"))
    normalized = recommendation.lower().rstrip(". ")
    action_required = bool(normalized) and normalized not in {no_action.lower(), "none", "n/a", "-"}
    return Reading(
        levels=levels,
        confidence=confidence,
        summary=_text(data.get("summary")),
        recommendation=recommendation if action_required else no_action,
        action_required=action_required,
    )


def apply_hysteresis(current_max: int, reading: Reading, pending: bool) -> tuple[bool, bool]:
    """Escalate at once, de-escalate only after two consecutive lower readings.

    Returns ``(write_levels, deescalation_pending)``. Confidence and texts are
    always written; only the levels wait for the confirmation.
    """
    if reading.max_level >= current_max:
        return True, False
    if not pending:
        return False, True
    return True, False


def cadence_minutes(level: int, active: bool, last_failed: bool = False) -> int:
    """Minutes to wait after the last analysis."""
    table = CADENCE_ACTIVE if active else CADENCE_IDLE
    minutes = table[max(0, min(MAX_LEVEL, level))]
    return min(minutes, RETRY_MIN) if last_failed else minutes


def level_name(level: int) -> str:
    """``none`` … ``critical``."""
    return LEVELS[max(0, min(MAX_LEVEL, level))]
