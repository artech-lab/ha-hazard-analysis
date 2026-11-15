"""Tests for the config and options flows."""

from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hazard_analysis.const import DOMAIN

from .common import CAMERAS, ENGINE, FALLBACK, add_engines

USER_INPUT = {"name": "Hazard monitor", "cameras": CAMERAS, "ai_task_entity": ENGINE}


async def test_user_flow(hass: HomeAssistant) -> None:
    add_engines(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM

    with patch("custom_components.hazard_analysis.monitor.HazardMonitor.async_start"):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], dict(USER_INPUT))
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Hazard monitor"
    assert result["data"]["cameras"] == CAMERAS
    assert hass.states.get("sensor.hazard_monitor_risk_level") is not None
    assert hass.states.get("button.hazard_monitor_analyze_now") is not None


async def test_user_flow_aborts_without_ai_task(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "no_ai_task"


async def test_user_flow_errors(hass: HomeAssistant) -> None:
    add_engines(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    bad = {**USER_INPUT, "cameras": [f"camera.view_{n}" for n in range(5)]}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], bad)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"cameras": "camera_count"}


async def test_options_flow(hass: HomeAssistant) -> None:
    add_engines(hass, ENGINE, FALLBACK)
    entry = MockConfigEntry(domain=DOMAIN, title="Hazard monitor", data={"cameras": CAMERAS, "ai_task_entity": ENGINE})
    entry.add_to_hass(hass)
    with patch("custom_components.hazard_analysis.monitor.HazardMonitor.async_start"):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        result = await hass.config_entries.options.async_init(entry.entry_id)
        assert result["type"] is FlowResultType.FORM
        same = {"cameras": CAMERAS, "ai_task_entity": ENGINE, "fallback_ai_task_entity": ENGINE, "save_evidence": True}
        result = await hass.config_entries.options.async_configure(result["flow_id"], same)
        assert result["errors"] == {"fallback_ai_task_entity": "same_engine"}

        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {**same, "fallback_ai_task_entity": FALLBACK, "save_evidence": False}
        )
        assert result["type"] is FlowResultType.CREATE_ENTRY
        await hass.async_block_till_done()
    monitor = entry.runtime_data
    assert monitor.engines == [ENGINE, FALLBACK]
    assert monitor.save_evidence is False
    assert monitor.occupancy is None
