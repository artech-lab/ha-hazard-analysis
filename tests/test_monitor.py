"""The monitor on a real Home Assistant core: fake AI answers in, entities and alerts out."""

from __future__ import annotations

import asyncio
from datetime import timedelta
import os
from pathlib import Path
import time
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.components.camera import Image
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, async_mock_service

from custom_components.hazard_analysis.const import CONFIG_VERSION, DOMAIN
from custom_components.hazard_analysis.monitor import HazardMonitor

from .common import CAMERAS, ENGINE, FALLBACK, SAFE, add_engines, reading

P = "hazard_monitor"


class FakeAI:
    """Replaces the ``ai_task.generate_data`` service."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.answers: dict[str, Any] = {ENGINE: SAFE}
        self.calls: list[dict[str, Any]] = []
        hass.services.async_register("ai_task", "generate_data", self._handle, supports_response=SupportsResponse.ONLY)

    async def _handle(self, call: ServiceCall) -> dict[str, Any]:
        self.calls.append(dict(call.data))
        answer = self.answers[call.data["entity_id"]]
        if answer == "hang":
            await asyncio.sleep(3600)
        if isinstance(answer, Exception):
            raise answer
        return {"conversation_id": "x", "data": answer}


@pytest.fixture
async def ai(hass: HomeAssistant) -> FakeAI:
    add_engines(hass, ENGINE, FALLBACK)
    assert await async_setup_component(hass, "ai_task", {})  # then override its service
    return FakeAI(hass)


async def _setup(hass: HomeAssistant, **options: Any) -> HazardMonitor:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hazard monitor",
        data={"cameras": CAMERAS, "ai_task_entity": ENGINE},
        options=options,
        version=CONFIG_VERSION,
    )
    entry.add_to_hass(hass)
    with patch.object(HazardMonitor, "async_start"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data


@pytest.fixture
def dirs(hass: HomeAssistant, tmp_path: Path) -> Path:
    """Temporary configuration folder, with the media folder inside."""
    hass.config.config_dir = str(tmp_path)
    hass.config.media_dirs = {"local": str(tmp_path / "media")}
    return tmp_path


def _old_file(path: Path, days: float) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"jpeg")
    stamp = time.time() - days * 86400
    os.utime(path, (stamp, stamp))
    return path


async def _analyze_critical(hass: HomeAssistant, ai: FakeAI, monitor: HazardMonitor) -> AsyncMock:
    ai.answers[ENGINE] = reading(smoke=4)
    get_image = AsyncMock(return_value=Image("image/jpeg", b"jpeg"))
    with patch("homeassistant.components.camera.async_get_image", get_image):
        await monitor.async_analyze()
        await hass.async_block_till_done()
    return get_image


def _state(hass: HomeAssistant, entity_id: str) -> str:
    return hass.states.get(entity_id).state


async def test_first_analysis_fills_every_entity(hass: HomeAssistant, ai: FakeAI) -> None:
    monitor = await _setup(hass)
    assert _state(hass, f"sensor.{P}_risk_level") == "unknown"

    assert await monitor.async_analyze()
    await hass.async_block_till_done()

    call = ai.calls[0]
    assert call["entity_id"] == ENGINE
    assert [a["media_content_id"] for a in call["attachments"]] == [f"media-source://camera/{c}" for c in CAMERAS]
    assert "minimum" not in str(call["structure"])  # some providers reject min/max
    assert _state(hass, f"sensor.{P}_risk_level") == "none"
    assert _state(hass, f"sensor.{P}_fire") == "0"
    assert _state(hass, f"sensor.{P}_confidence") == "9"
    assert _state(hass, f"sensor.{P}_summary") == "The area looks clear."
    reco = hass.states.get(f"sensor.{P}_recommendation")
    assert reco.state == "No action needed" and reco.attributes["action_required"] is False
    assert _state(hass, f"binary_sensor.{P}_hazard") == "off"
    assert _state(hass, f"binary_sensor.{P}_problem") == "off"
    assert _state(hass, f"sensor.{P}_last_analysis") != "unknown"


async def test_escalate_at_once_deescalate_after_two_readings(hass: HomeAssistant, ai: FakeAI) -> None:
    monitor = await _setup(hass, save_evidence=False)
    ai.answers[ENGINE] = reading(fire=3, recommendation="Switch off the soldering iron")
    await monitor.async_analyze()
    await hass.async_block_till_done()
    assert _state(hass, f"sensor.{P}_risk_level") == "high"
    assert _state(hass, f"binary_sensor.{P}_hazard") == "on"

    ai.answers[ENGINE] = SAFE
    await monitor.async_analyze()
    await hass.async_block_till_done()
    assert _state(hass, f"sensor.{P}_fire") == "3"  # kept
    assert _state(hass, f"binary_sensor.{P}_deescalation_pending") == "on"
    assert _state(hass, f"sensor.{P}_summary") == "The area looks clear."  # texts always written

    await monitor.async_analyze()
    await hass.async_block_till_done()
    assert _state(hass, f"sensor.{P}_fire") == "0"
    assert _state(hass, f"binary_sensor.{P}_deescalation_pending") == "off"


async def test_invalid_response_keeps_values(hass: HomeAssistant, ai: FakeAI) -> None:
    monitor = await _setup(hass)
    await monitor.async_analyze()
    ai.answers[ENGINE] = {"fire": "lots", "summary": "?"}
    ai.answers[FALLBACK] = {"summary": "incomplete"}
    assert not await monitor.async_analyze()
    await hass.async_block_till_done()
    assert _state(hass, f"sensor.{P}_summary") == "The area looks clear."
    problem = hass.states.get(f"binary_sensor.{P}_problem")
    assert problem.state == "on"
    assert "invalid response" in problem.attributes["last_error"]


async def test_hanging_engine_falls_back(hass: HomeAssistant, ai: FakeAI) -> None:
    monitor = await _setup(hass, fallback_ai_task_entity=FALLBACK)
    ai.answers[ENGINE] = "hang"
    ai.answers[FALLBACK] = reading(other=1)
    with patch("custom_components.hazard_analysis.monitor.ANALYSIS_TIMEOUT_S", 0.05):
        assert await monitor.async_analyze()
    await hass.async_block_till_done()
    assert _state(hass, f"sensor.{P}_other") == "1"
    assert monitor.last_engine == FALLBACK


async def test_unavailable_engine_is_tried_last(hass: HomeAssistant, ai: FakeAI) -> None:
    monitor = await _setup(hass, fallback_ai_task_entity=FALLBACK)
    hass.states.async_set(ENGINE, "unavailable")
    ai.answers[FALLBACK] = SAFE
    await monitor.async_analyze()
    assert [call["entity_id"] for call in ai.calls] == [FALLBACK]


async def test_alerts_and_evidence(hass: HomeAssistant, ai: FakeAI, dirs: Path) -> None:
    pushes = async_mock_service(hass, "notify", "mobile_app_phone")
    monitor = await _setup(hass, notify_services=["mobile_app_phone"], save_evidence=True)
    ai.answers[ENGINE] = reading(smoke=4, summary="Dense smoke near the bench", recommendation="Leave the room")
    image = Image("image/jpeg", b"jpeg")
    with patch("homeassistant.components.camera.async_get_image", AsyncMock(return_value=image)):
        await monitor.async_analyze()
        await hass.async_block_till_done()

    assert len(pushes) == 1
    assert pushes[0].data["title"].startswith("🚨")
    assert "Leave the room" in pushes[0].data["message"]
    assert pushes[0].data["data"]["image"] == f"/api/camera_proxy/{CAMERAS[0]}"
    files = sorted((dirs / "hazard_analysis" / "evidence").iterdir())
    assert files == sorted(dirs.rglob("*.jpg"))  # nowhere else
    assert len(files) == 2 and all("-critical-camera" in path.name for path in files)

    ai.answers[ENGINE] = SAFE
    await monitor.async_analyze()
    await monitor.async_analyze()
    await hass.async_block_till_done()
    assert len(pushes) == 2
    assert pushes[1].data["title"].startswith("✅")


@pytest.mark.parametrize("options", [{}, {"save_evidence": False}])
async def test_no_evidence_unless_enabled(hass: HomeAssistant, ai: FakeAI, dirs: Path, options: dict[str, Any]) -> None:
    monitor = await _setup(hass, **options)
    assert monitor.save_evidence is False
    get_image = await _analyze_critical(hass, ai, monitor)
    monitor._on_prune()
    await hass.async_block_till_done(wait_background_tasks=True)
    get_image.assert_not_called()
    assert monitor.alert_state == "critical"
    assert not (dirs / "hazard_analysis").exists()
    assert not (dirs / "media").exists()
    assert not list(dirs.rglob("*.jpg"))


async def test_evidence_custom_path(hass: HomeAssistant, ai: FakeAI, dirs: Path) -> None:
    folder = dirs / "private"
    monitor = await _setup(hass, save_evidence=True, evidence_path=str(folder))
    await _analyze_critical(hass, ai, monitor)
    assert len(list(folder.iterdir())) == 2
    assert str(folder) not in str(monitor.diagnostics())

    # The folder is still pruned after the path changes.
    entry = monitor.entry
    with patch.object(HazardMonitor, "async_start"):
        hass.config_entries.async_update_entry(entry, options={"save_evidence": False})
        await hass.async_block_till_done()
    assert entry.runtime_data is not monitor
    for path in folder.iterdir():
        _old_file(path, 16)
    entry.runtime_data._on_prune()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert list(folder.iterdir()) == []


@pytest.mark.parametrize("public", ["media", "www"])
async def test_evidence_never_in_public_folders(hass: HomeAssistant, ai: FakeAI, dirs: Path, public: str) -> None:
    monitor = await _setup(hass, save_evidence=True, evidence_path=str(dirs / public / "x"))
    await _analyze_critical(hass, ai, monitor)
    assert not (dirs / public).exists()
    assert monitor.alert_state == "critical"


async def test_evidence_write_error_does_not_stop_the_alert(hass: HomeAssistant, ai: FakeAI, dirs: Path) -> None:
    monitor = await _setup(hass, save_evidence=True)
    with patch.object(Path, "write_bytes", side_effect=OSError("disk full")):
        await _analyze_critical(hass, ai, monitor)
    assert monitor.alert_state == "critical"


@pytest.mark.parametrize("save", [True, False])
async def test_prune_by_age_only_own_files(hass: HomeAssistant, ai: FakeAI, dirs: Path, save: bool) -> None:
    monitor = await _setup(hass, save_evidence=save, evidence_retention_days=5)
    other = MockConfigEntry(domain=DOMAIN, title="Other area", version=CONFIG_VERSION)
    other.add_to_hass(hass)
    folder = dirs / "hazard_analysis" / "evidence"
    media = dirs / "media" / "hazard_analysis"
    name = "20260101-120000-high-camera1.jpg"
    own = f"hazard_analysis-{monitor.entry.entry_id}-{name}"
    legacy = "20260101-120000-critical-area_north.jpg"
    expired = [
        _old_file(folder / own, 6),
        _old_file(media / P / legacy, 6),
        _old_file(media / "former_title" / legacy, 6),
    ]
    kept = [
        _old_file(folder / own.replace("camera1", "camera2"), 4),
        _old_file(folder / f"hazard_analysis-{other.entry_id}-{name}", 6),
        _old_file(folder / "holiday.jpg", 99),
        _old_file(folder / "sub" / own, 99),
        _old_file(media / P / legacy.replace("north", "south"), 4),
        _old_file(media / P / "holiday.jpg", 99),
        _old_file(media / "other_area" / legacy, 6),
        _old_file(media.parent / legacy, 99),
    ]
    monitor._on_prune()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not any(path.exists() for path in expired)
    assert all(path.exists() for path in kept)


async def test_prune_at_startup_and_daily(hass: HomeAssistant, ai: FakeAI, dirs: Path, freezer) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hazard monitor",
        data={"cameras": CAMERAS, "ai_task_entity": ENGINE},
        version=CONFIG_VERSION,
    )
    entry.add_to_hass(hass)
    name = f"hazard_analysis-{entry.entry_id}-20260101-120000-high-camera1.jpg"
    path = _old_file(dirs / "hazard_analysis" / "evidence" / name, 16)  # default: 15 days
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not path.exists()

    _old_file(path, 16)
    now = dt_util.now()
    due = now.replace(hour=3, minute=17, second=0, microsecond=0)
    if due <= now:
        due += timedelta(days=1)
    freezer.move_to(due)
    async_fire_time_changed(hass, due)
    await hass.async_block_till_done(wait_background_tasks=True)
    assert not path.exists()
    assert await hass.config_entries.async_unload(entry.entry_id)


@pytest.mark.parametrize(
    ("options", "expected"),
    [({}, False), ({"save_evidence": True}, True), ({"save_evidence": False}, False), ({"notify_services": []}, False)],
)
async def test_migration(hass: HomeAssistant, ai: FakeAI, dirs: Path, options: dict[str, Any], expected: bool) -> None:
    media_file = _old_file(dirs / "media" / "hazard_analysis" / P / "20260101-120000-high-area_north.jpg", 1)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Hazard monitor",
        data={"cameras": CAMERAS, "ai_task_entity": ENGINE},
        options=options,
        version=1,
    )
    entry.add_to_hass(hass)
    with patch.object(HazardMonitor, "async_start"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    assert entry.version == CONFIG_VERSION
    assert entry.options == {**options, "save_evidence": expected}
    assert entry.runtime_data.save_evidence is expected
    entry.runtime_data._on_prune()
    await hass.async_block_till_done(wait_background_tasks=True)
    assert media_file.exists()  # neither moved nor deleted before it expires


async def test_newer_entry_is_refused(hass: HomeAssistant, ai: FakeAI) -> None:
    entry = MockConfigEntry(domain=DOMAIN, version=CONFIG_VERSION + 1)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)


async def test_schedule(hass: HomeAssistant, ai: FakeAI) -> None:
    hass.states.async_set("binary_sensor.area_occupancy", "off")
    monitor = await _setup(hass, occupancy_entity="binary_sensor.area_occupancy")
    assert monitor.next_due() is None
    await monitor.async_analyze()
    assert monitor.next_due() - monitor.last_attempt == timedelta(minutes=60)  # idle, nothing found
    hass.states.async_set("binary_sensor.area_occupancy", "on")
    assert monitor.next_due() - monitor.last_attempt == timedelta(minutes=15)

    ai.answers[ENGINE] = reading(flood=2)
    await monitor.async_analyze()
    assert monitor.next_due() - monitor.last_attempt == timedelta(minutes=5)

    ai.answers[ENGINE] = {}
    await monitor.async_analyze()
    assert monitor.next_due() - monitor.last_attempt == timedelta(minutes=5)  # retry


async def test_tick_respects_monitoring_switch(hass: HomeAssistant, ai: FakeAI) -> None:
    monitor = await _setup(hass)
    await hass.services.async_call("switch", "turn_off", {"entity_id": f"switch.{P}_monitoring"}, blocking=True)
    monitor._on_tick()
    await hass.async_block_till_done()
    assert ai.calls == []

    await hass.services.async_call("switch", "turn_on", {"entity_id": f"switch.{P}_monitoring"}, blocking=True)
    await hass.async_block_till_done()
    assert len(ai.calls) == 1

    monitor.last_attempt = dt_util.utcnow() - timedelta(minutes=5)
    monitor._on_tick()
    await hass.async_block_till_done()
    assert len(ai.calls) == 1  # not due yet (15 min)


async def test_button_and_restore(hass: HomeAssistant, ai: FakeAI) -> None:
    monitor = await _setup(hass, save_evidence=False)
    ai.answers[ENGINE] = reading(accident=2)
    await hass.services.async_call("button", "press", {"entity_id": f"button.{P}_analyze_now"}, blocking=True)
    await hass.async_block_till_done()
    assert _state(hass, f"sensor.{P}_accident") == "2"

    entry = monitor.entry
    await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert _state(hass, f"sensor.{P}_accident") == "2"
    assert _state(hass, f"sensor.{P}_risk_level") == "medium"


async def test_start_runs_first_analysis_then_unloads(hass: HomeAssistant, ai: FakeAI, freezer) -> None:
    entry = MockConfigEntry(domain=DOMAIN, title="Hazard monitor", data={"cameras": CAMERAS, "ai_task_entity": ENGINE})
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert ai.calls == []

    freezer.tick(timedelta(seconds=31))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(ai.calls) == 1

    assert await hass.config_entries.async_unload(entry.entry_id)
    freezer.tick(timedelta(minutes=30))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert len(ai.calls) == 1
