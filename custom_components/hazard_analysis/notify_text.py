# SPDX-License-Identifier: GPL-3.0-or-later
"""Texts of the alerts (persistent notification and push), English and Italian.

Home Assistant translation files have no section for free-form notification
texts, so they live here; a test checks that both languages have the same keys.
"""

from __future__ import annotations

STRINGS: dict[str, dict[str, str]] = {
    "en": {
        "critical_title": "🚨 Critical hazard: {name}",
        "high_title": "⚠️ High hazard: {name}",
        "clear_title": "✅ Hazard cleared: {name}",
        "clear_message": "Risk is back below the alert level.",
        "action": "Action: {text}",
        "fire": "fire",
        "smoke": "smoke",
        "flood": "flood",
        "accident": "accident",
        "other": "other",
    },
    "it": {
        "critical_title": "🚨 Rischio critico: {name}",
        "high_title": "⚠️ Rischio alto: {name}",
        "clear_title": "✅ Rischio rientrato: {name}",
        "clear_message": "Il rischio è tornato sotto la soglia di allarme.",
        "action": "Azione: {text}",
        "fire": "incendio",
        "smoke": "fumo",
        "flood": "allagamento",
        "accident": "incidente",
        "other": "altro",
    },
}


def text(language: str | None, key: str, **values: str) -> str:
    """Localized text, English as fallback."""
    table = STRINGS.get(str(language or "en").lower().split("-")[0], STRINGS["en"])
    return table.get(key, STRINGS["en"][key]).format(**values)
