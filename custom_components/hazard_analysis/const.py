# SPDX-License-Identifier: GPL-3.0-or-later
"""Constants for the Hazard Analysis integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "hazard_analysis"
DEFAULT_NAME: Final = "Hazard monitor"

# Bundled dashboard card
CARD_FILENAME: Final = "hazard-analysis-card.js"
CARD_URL: Final = f"/{DOMAIN}/{CARD_FILENAME}"

# Config entry keys
CONF_CAMERAS: Final = "cameras"
CONF_AI_TASK: Final = "ai_task_entity"
CONF_FALLBACK_AI_TASK: Final = "fallback_ai_task_entity"
CONF_OCCUPANCY: Final = "occupancy_entity"
CONF_WORKDAY: Final = "workday_entity"
CONF_ENV_SENSORS: Final = "environment_sensors"
CONF_AREA_DESCRIPTION: Final = "area_description"
CONF_NOTIFY: Final = "notify_services"
CONF_SAVE_EVIDENCE: Final = "save_evidence"

MAX_CAMERAS: Final = 4

# ------------------------------------------------------------------ hazards
# Order used by the prompt, the entities and the card.
HAZARDS: Final = ("fire", "smoke", "flood", "accident", "other")
LEVELS: Final = ("none", "low", "medium", "high", "critical")
MAX_LEVEL: Final = 4
MAX_CONFIDENCE: Final = 10
ALERT_LEVEL: Final = 3  # "high": push alert, evidence snapshots, hazard binary sensor on
MAX_TEXT: Final = 255  # Home Assistant state length limit

# ------------------------------------------------------------------ cadence
# Minutes between two analyses, by the current highest level. "active" applies
# when the occupancy or workday entity is on (or when neither is configured);
# "idle" keeps a slower 24/7 baseline. From "medium" up the two coincide: a real
# risk is urgent at any hour.
CADENCE_ACTIVE: Final = (15, 10, 5, 2, 1)
CADENCE_IDLE: Final = (60, 30, 5, 2, 1)
OCCUPANCY_COOLDOWN_MIN: Final = 10  # extra analysis when the area becomes occupied
RETRY_MIN: Final = 5  # after a failed analysis
STALE_MIN: Final = 90  # no successful analysis for this long -> problem sensor on
STARTUP_DELAY_S: Final = 30

# ------------------------------------------------------------------- engine
# The AI Task call is wrapped in a hard timeout: a backend that accepts the
# connection and never answers would otherwise block every later analysis.
ANALYSIS_TIMEOUT_S: Final = 180
TASK_NAME: Final = "Hazard analysis"

# ----------------------------------------------------------------- evidence
EVIDENCE_FOLDER: Final = "hazard_analysis"
EVIDENCE_DAYS: Final = 30

STORAGE_VERSION: Final = 1
