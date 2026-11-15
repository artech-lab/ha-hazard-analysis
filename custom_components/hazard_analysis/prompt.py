# SPDX-License-Identifier: GPL-3.0-or-later
"""Instructions and output structure sent to the AI Task entity.

Pure module: the caller passes already-resolved camera names, sensor readings
and language, so the prompt can be tested without Home Assistant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .const import HAZARDS

LANGUAGES: dict[str, tuple[str, str]] = {
    # code: (language name for the model, exact "no action" phrase)
    "en": ("English", "No action needed"),
    "it": ("Italian", "Nessuna azione necessaria"),
}

# Reference ranges by sensor device class, used only as corroboration.
REFERENCE_RANGES: dict[str, str] = {
    "pm10": "normal < 25 µg/m³, moderate 25-50, high 51-100, critical > 100",
    "pm25": "normal < 15 µg/m³, moderate 15-35, high 36-75, critical > 75",
    "carbon_dioxide": "normal < 1000 ppm, moderate 1000-2000, high 2001-5000, critical > 5000",
    "carbon_monoxide": "normal < 9 ppm, moderate 9-35, high 36-100, critical > 100",
    "volatile_organic_compounds": "normal < 500 µg/m³, moderate 500-1000, high 1001-3000, critical > 3000",
    "temperature": "normal 10-35 °C, elevated 36-50, high 51-80, critical > 80",
    "humidity": "normal 30-70 %, a sudden rise near the floor may corroborate a leak",
    "moisture": "on = water detected",
    "smoke": "on = smoke detected",
    "gas": "on = gas detected",
}


@dataclass(frozen=True, slots=True)
class SensorReading:
    """An environment sensor as seen by the model."""

    name: str
    value: str
    unit: str | None = None
    device_class: str | None = None


def language(code: str | None) -> tuple[str, str]:
    """Model language name and "no action" phrase for a Home Assistant language."""
    return LANGUAGES.get(str(code or "en").lower().split("-")[0], LANGUAGES["en"])


def structure() -> dict[str, Any]:
    """Structured output for ``ai_task.generate_data``.

    Number fields carry no ``min``/``max``: some providers reject them in
    structured-output schemas. The ranges are enforced by ``parse_reading``.
    """
    fields: dict[str, Any] = {
        key: {
            "description": f"{key.capitalize()} hazard level: 0=none, 1=low, 2=medium, 3=high, 4=critical",
            "required": True,
            "selector": {"number": {"mode": "box"}},
        }
        for key in HAZARDS
    }
    fields["confidence"] = {
        "description": "Clarity of the evidence, from 1 (very uncertain) to 10 (certain)",
        "required": True,
        "selector": {"number": {"mode": "box"}},
    }
    fields["summary"] = {
        "description": "Brief factual justification of the scores (max 250 characters)",
        "required": True,
        "selector": {"text": {"multiline": True}},
    }
    fields["recommendation"] = {
        "description": "Short corrective action (max 200 characters), or the exact no-action phrase",
        "required": True,
        "selector": {"text": {"multiline": True}},
    }
    return fields


def _sensor_block(sensors: list[SensorReading]) -> str:
    if not sensors:
        return "No environment sensors are available: score on visual evidence only."
    lines = []
    for sensor in sensors:
        value = f"{sensor.value} {sensor.unit}".strip() if sensor.unit else sensor.value
        line = f"- **{sensor.name}**: {value}"
        if sensor.device_class in REFERENCE_RANGES:
            line += f" (reference: {REFERENCE_RANGES[sensor.device_class]})"
        lines.append(line)
    lines.append("If a value is `unknown` or `unavailable`, ignore that sensor and mention it in the summary.")
    return "\n".join(lines)


def instructions(
    cameras: list[str],
    sensors: list[SensorReading],
    language_code: str | None,
    area_description: str | None = None,
) -> str:
    """Full instructions for one analysis."""
    lang, no_action = language(language_code)
    views = "\n".join(f"{index}. {name}" for index, name in enumerate(cameras, start=1))
    area = (area_description or "").strip()
    area_line = f"\n**Area description (context only, never evidence):** {area}\n" if area else ""
    return f"""# Workspace safety hazard detection

You are a high-precision safety hazard detection system for a workspace (laboratory, workshop,
garage or similar). Analyse the attached images and the environment sensor data. The images are
{len(cameras)} camera view(s) of the same area, in this order:

{views}
{area_line}
Score each hazard category on the combined evidence of all views, using the highest level seen in
any image. Detect BOTH active incidents AND clearly visible precursor conditions that could credibly
escalate into an incident. Operate with extreme precision and zero assumptions.

## Core rules

1. **Evidence only.** Flag a hazard only on direct, unambiguous visual evidence or sensor values out
   of range. Never infer risk from the mere presence of people, objects or context.
2. **Independent categories.** Evaluate every category on its own evidence.
3. **No hallucination.** No clear evidence and normal sensors means `0`.
4. **Small flames count.** Any visible flame, ember, spark or ignition source scores at least `2`
   in `fire`; in an industrial, workshop or outdoor setting at least `3`.
5. **Stress is an internal modifier only.** Evaluate visible worker stress internally; it must never
   appear in the output. Acute stress or panic may raise `accident` by +1 only when combined with a
   physically dangerous position (machinery, height, live cables, hazardous materials) and not
   already counted. A calm or neutral person never raises any score.
6. **Post-event accidents count.** A person on the ground, displaced PPE, a fallen ladder or a
   distress posture near machinery is a probable post-accident condition: do not score `0` only
   because the immediate threat has passed.
7. **Confidence is clarity, not emptiness.** A clear image of a safe scene can score 9.
   Visible hazards without sensor data should not exceed 7.
8. **Proactive precursor detection.** Score clearly visible precursors `1` (latent) or `2`
   (credible escalation path) in their most relevant category. The precursor itself must be visible.

## Environment sensors

Use them as corroboration only, never as the sole reason for a score.

{_sensor_block(sensors)}

## Scale (every category)

| Score | Label | Meaning |
|---|---|---|
| 0 | none | No visible evidence; sensors normal |
| 1 | low | Minor issue or latent precursor |
| 2 | medium | Notable risk or credible escalation path |
| 3 | high | Serious and immediate danger |
| 4 | critical | Severe, life-threatening condition |

## Categories

- **fire**: flames of any size, embers, sparks, glowing materials, heat damage with an active
  ignition source. Corroborate with temperature. Independent from smoke.
- **smoke**: visible smoke, plumes or haze from burning or smouldering material. Corroborate with
  particulate sensors. Independent from fire.
- **flood**: water on floors, submerged equipment, leaks causing pooling, waterlogged surfaces.
- **accident**: a person lying on the ground or unable to support themselves, blood or wounds,
  entrapment or entanglement, an active collision, or the post-event signs above (minimum `2`).
- **other**: any other clearly visible safety violation: exposed or damaged cables, structural
  instability, chemical spills or unlabelled containers, blocked exits, unsecured heavy objects at
  height, missing PPE where clearly required, tools left in unsafe positions. Elevated CO2 without a
  visible cause may contribute.

## Precursors

- fire 1-2: soldering iron, hot-air station, hot plate or heater left on unattended, especially near
  paper, cardboard, plastics or solvents; batteries (LiPo) charging unattended, swollen packs or
  packs charging on a flammable surface; scorch marks, melted insulation, discoloured connectors.
- other 1-2: overloaded or daisy-chained power strips; cables across walkways; blocked emergency
  exit, extinguisher or electrical panel (minimum `2`); unstable stacking; sharp tools at a bench
  edge; open containers of chemicals or solvents.
- flood 1: dripping pipes or fittings; liquids on or next to powered electronics (also other 1-2).
- accident 1-2: a person standing on a chair or improvised support; working at height without
  stable support; missing PPE where clearly required.

An empty, tidy scene has no precursors. Never invent them.

## Text fields

- **summary**: written in {lang}, at most 250 characters: the concrete visual or sensor evidence
  behind the highest score or the most relevant precursor. If every score is 0, say that the area
  looks clear. Never mention the internal stress evaluation.
- **recommendation**: written in {lang}, at most 200 characters: one actionable corrective step for
  the highest risk or the most relevant precursor. If nothing requires action, return exactly
  "{no_action}".
"""
