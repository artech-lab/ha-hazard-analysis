"""Tests for the config and options flows."""

from pathlib import Path
from unittest.mock import patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.hazard_analysis.const import CONFIG_VERSION, DOMAIN

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
    assert result["data"]["save_evidence"] is False
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
    assert monitor.evidence_days == 15


async def _options_form(hass: HomeAssistant, tmp_path: Path) -> str:
    hass.config.config_dir = str(tmp_path)
    hass.config.media_dirs = {"local": str(tmp_path / "media")}
    add_engines(hass)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hazard monitor",
        data={"cameras": CAMERAS, "ai_task_entity": ENGINE},
        version=CONFIG_VERSION,
    )
    entry.add_to_hass(hass)
    return (await hass.config_entries.options.async_init(entry.entry_id))["flow_id"]


@pytest.mark.parametrize(
    ("folder", "error"),
    [
        ("relative/path", "evidence_path_absolute"),
        ("{tmp}/media", "evidence_path_media"),
        ("{tmp}/private/../media/x", "evidence_path_media"),
        ("{tmp}/link", "evidence_path_media"),
        ("{tmp}/www/evidence", "evidence_path_www"),
        ("{tmp}/file", "evidence_path_not_writable"),
    ],
)
async def test_options_flow_refuses_evidence_path(hass: HomeAssistant, tmp_path: Path, folder: str, error: str) -> None:
    (tmp_path / "file").touch()
    (tmp_path / "link").symlink_to(tmp_path / "media")
    flow_id = await _options_form(hass, tmp_path)
    user_input = {"cameras": CAMERAS, "ai_task_entity": ENGINE, "save_evidence": True}
    result = await hass.config_entries.options.async_configure(
        flow_id, {**user_input, "evidence_path": folder.format(tmp=tmp_path)}
    )
    assert result["errors"] == {"evidence_path": error}
    assert not (tmp_path / "media").exists() and not (tmp_path / "www").exists()


@pytest.mark.parametrize("save", [True, False])
async def test_options_flow_accepts_evidence_path(hass: HomeAssistant, tmp_path: Path, save: bool) -> None:
    flow_id = await _options_form(hass, tmp_path)
    folder = tmp_path / "private" / "evidence"
    result = await hass.config_entries.options.async_configure(
        flow_id,
        {
            "cameras": CAMERAS,
            "ai_task_entity": ENGINE,
            "save_evidence": save,
            "evidence_path": f" {folder} ",
            "evidence_retention_days": 7,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"]["evidence_path"] == str(folder)
    assert result["data"]["evidence_retention_days"] == 7
    assert folder.is_dir() is save  # created only when saving is enabled
    assert not save or list(folder.iterdir()) == []


@pytest.mark.parametrize("days", [0, 366])
async def test_options_flow_retention_range(hass: HomeAssistant, tmp_path: Path, days: int) -> None:
    flow_id = await _options_form(hass, tmp_path)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            flow_id,
            {"cameras": CAMERAS, "ai_task_entity": ENGINE, "save_evidence": False, "evidence_retention_days": days},
        )


async def test_user_flow_refuses_public_default_folder(hass: HomeAssistant, tmp_path: Path) -> None:
    add_engines(hass)
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    hass.config.config_dir = str(tmp_path)
    hass.config.media_dirs = {"local": str(tmp_path)}  # the whole configuration folder is a media folder
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {**USER_INPUT, "save_evidence": True})
    assert result["errors"] == {"save_evidence": "evidence_path_media"}
