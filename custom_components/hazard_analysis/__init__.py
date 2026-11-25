# SPDX-License-Identifier: GPL-3.0-or-later
"""Hazard Analysis: AI safety monitoring of a workspace from its cameras."""

from __future__ import annotations

from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.typing import ConfigType
from homeassistant.loader import async_get_integration

from .const import CARD_FILENAME, CARD_URL, CONF_SAVE_EVIDENCE, CONFIG_VERSION, DEFAULT_SAVE_EVIDENCE, DOMAIN
from .monitor import HazardMonitor

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.BUTTON, Platform.SENSOR, Platform.SWITCH]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

type HazardConfigEntry = ConfigEntry[HazardMonitor]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the bundled dashboard card and load it in every dashboard.

    The version in ``manifest.json`` is the single source of truth: it is
    appended to the card URL, which busts the browser cache after an update
    and tells the card its own version.
    """
    version = str((await async_get_integration(hass, DOMAIN)).version)
    hass.data[DOMAIN] = version
    card = Path(__file__).parent / "frontend" / CARD_FILENAME
    await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), cache_headers=False)])
    add_extra_js_url(hass, f"{CARD_URL}?v={version}")
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: HazardConfigEntry) -> bool:
    """Migrate an entry created by an older version.

    1 -> 2: evidence snapshots became opt-in. A choice already stored in the
    options is kept; otherwise the new default applies.
    """
    if entry.version > CONFIG_VERSION:
        return False
    if entry.version < CONFIG_VERSION:
        hass.config_entries.async_update_entry(
            entry, options={CONF_SAVE_EVIDENCE: DEFAULT_SAVE_EVIDENCE, **entry.options}, version=CONFIG_VERSION
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: HazardConfigEntry) -> bool:
    """Set up a hazard monitor from a config entry."""
    monitor = HazardMonitor(hass, entry, hass.data[DOMAIN])
    await monitor.async_load()
    entry.runtime_data = monitor

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    monitor.async_start()
    entry.async_on_unload(entry.add_update_listener(_async_reload))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: HazardConfigEntry) -> bool:
    """Unload a config entry."""
    if unloaded := await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        await entry.runtime_data.async_stop()
    return unloaded


async def _async_reload(hass: HomeAssistant, entry: HazardConfigEntry) -> None:
    """Reload when the options change."""
    await hass.config_entries.async_reload(entry.entry_id)
