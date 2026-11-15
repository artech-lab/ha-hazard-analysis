"""Pure functions: validation, hysteresis, cadence, prompt."""

import pytest

from custom_components.hazard_analysis.analysis import (
    InvalidResponse,
    apply_hysteresis,
    cadence_minutes,
    level_name,
    parse_reading,
)
from custom_components.hazard_analysis.const import HAZARDS
from custom_components.hazard_analysis.prompt import SensorReading, instructions, language, structure

from .common import SAFE, reading

NO_ACTION = "No action needed"


def test_parse_clamps_out_of_range_numbers() -> None:
    result = parse_reading(reading(fire=7, smoke=-2, flood="2", accident=2.6, confidence=14), NO_ACTION)
    assert result.levels == {"fire": 4, "smoke": 0, "flood": 2, "accident": 3, "other": 0}
    assert result.confidence == 10
    assert result.max_level == 4


@pytest.mark.parametrize("bad", [{"fire": None}, {"fire": "high"}, {"confidence": True}, {"other": float("nan")}])
def test_parse_rejects_missing_or_non_numeric(bad) -> None:
    with pytest.raises(InvalidResponse):
        parse_reading(reading(**bad), NO_ACTION)
    with pytest.raises(InvalidResponse):
        parse_reading({key: value for key, value in SAFE.items() if key != "smoke"}, NO_ACTION)
    with pytest.raises(InvalidResponse):
        parse_reading(None, NO_ACTION)


def test_parse_texts() -> None:
    result = parse_reading(reading(summary="  a\n b  " + "x" * 400), NO_ACTION)
    assert result.summary.startswith("a b") and len(result.summary) == 255
    assert result.action_required is False and result.recommendation == NO_ACTION
    for none in ("no action needed.", "NONE", ""):
        assert parse_reading(reading(recommendation=none), NO_ACTION).action_required is False
    act = parse_reading(reading(recommendation="Clear the exit"), NO_ACTION)
    assert act.action_required is True and act.recommendation == "Clear the exit"


def test_hysteresis() -> None:
    high = parse_reading(reading(fire=3), NO_ACTION)
    low = parse_reading(SAFE, NO_ACTION)
    assert apply_hysteresis(0, high, False) == (True, False)  # escalate
    assert apply_hysteresis(3, high, True) == (True, False)  # equal: write, clear the flag
    assert apply_hysteresis(3, low, False) == (False, True)  # first lower reading: wait
    assert apply_hysteresis(3, low, True) == (True, False)  # confirmed


def test_cadence() -> None:
    assert [cadence_minutes(level, True) for level in range(5)] == [15, 10, 5, 2, 1]
    assert [cadence_minutes(level, False) for level in range(5)] == [60, 30, 5, 2, 1]
    assert cadence_minutes(0, False, last_failed=True) == 5
    assert cadence_minutes(4, False, last_failed=True) == 1
    assert level_name(9) == "critical" and level_name(-1) == "none"


def test_structure_has_no_numeric_bounds() -> None:
    fields = structure()
    assert set(fields) == {*HAZARDS, "confidence", "summary", "recommendation"}
    for field in fields.values():
        assert field["required"] is True
        assert set(field["selector"].get("number", {})) <= {"mode"}


def test_instructions() -> None:
    text = instructions(
        ["North view", "South view"],
        [SensorReading("Lab PM10", "31", "µg/m³", "pm10"), SensorReading("Door", "unavailable")],
        "it-IT",
        "electronics lab",
    )
    assert "1. North view\n2. South view" in text
    assert "written in Italian" in text and '"Nessuna azione necessaria"' in text
    assert "**Lab PM10**: 31 µg/m³ (reference: normal < 25" in text
    assert "electronics lab" in text
    assert "No environment sensors" in instructions(["A"], [], "en", None)
    assert language("de") == language("en")
