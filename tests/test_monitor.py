"""The monitor on a real Home Assistant core: fake AI answers in, entities and alerts out."""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.components.camera import Image
from homeassistant.core import HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed, async_mock_service

from custom_components.hazard_analysis.const import DOMAIN
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
    )
    entry.add_to_hass(hass)
    with patch.object(HazardMonitor, "async_start"):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    return entry.runtime_data


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


async def test_alerts_and_evidence(hass: HomeAssistant, ai: FakeAI, tmp_path) -> None:
    hass.config.media_dirs = {"local": str(tmp_path)}
    pushes = async_mock_service(hass, "notify", "mobile_app_phone")
    monitor = await _setup(hass, notify_services=["mobile_app_phone"])
    ai.answers[ENGINE] = reading(smoke=4, summary="Dense smoke near the bench", recommendation="Leave the room")
    image = Image("image/jpeg", b"jpeg")
    with patch("homeassistant.components.camera.async_get_image", AsyncMock(return_value=image)):
        await monitor.async_analyze()
        await hass.async_block_till_done()

    assert len(pushes) == 1
    assert pushes[0].data["title"].startswith("🚨")
    assert "Leave the room" in pushes[0].data["message"]
    assert pushes[0].data["data"]["image"] == f"/api/camera_proxy/{CAMERAS[0]}"
    files = sorted(path.name for path in tmp_path.rglob("*.jpg"))
    assert len(files) == 2 and all("-critical-" in name for name in files)

    ai.answers[ENGINE] = SAFE
    await monitor.async_analyze()
    await monitor.async_analyze()
    await hass.async_block_till_done()
    assert len(pushes) == 2
    assert pushes[1].data["title"].startswith("✅")


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
