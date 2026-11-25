# SPDX-License-Identifier: GPL-3.0-or-later
"""Diagnostics support for Hazard Analysis."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from . import HazardConfigEntry
from .const import CONF_AREA_DESCRIPTION, CONF_CAMERAS, CONF_EVIDENCE_PATH, CONF_NOTIFY, CONF_OCCUPANCY

TO_REDACT = {CONF_AREA_DESCRIPTION, CONF_CAMERAS, CONF_EVIDENCE_PATH, CONF_NOTIFY, CONF_OCCUPANCY}


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: HazardConfigEntry) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    return {
        "config": async_redact_data({**entry.data, **entry.options}, TO_REDACT),
        "monitor": entry.runtime_data.diagnostics(),
    }
