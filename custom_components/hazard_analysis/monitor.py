# SPDX-License-Identifier: GPL-3.0-or-later
"""Analysis engine for Hazard Analysis.

One ``HazardMonitor`` per config entry does the whole job:

    schedule -> camera images + sensors -> AI Task (timeout, fallback)
    -> validation -> hysteresis -> entities, alerts, evidence snapshots

It persists its state with ``Store`` so levels, texts and timestamps survive
a restart, and it never needs helpers, templates or automations.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from datetime import datetime, timedelta
import logging
from pathlib import Path
import re
import tempfile
import time
from typing import Any

from homeassistant.components import camera, persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    ATTR_DEVICE_CLASS,
    ATTR_FRIENDLY_NAME,
    ATTR_UNIT_OF_MEASUREMENT,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import CALLBACK_TYPE, Event, EventStateChangedData, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_change,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util, slugify
import voluptuous as vol

from . import notify_text
from .analysis import InvalidResponse, Reading, apply_hysteresis, cadence_minutes, level_name, parse_reading
from .const import (
    ALERT_LEVEL,
    ANALYSIS_TIMEOUT_S,
    CONF_AI_TASK,
    CONF_AREA_DESCRIPTION,
    CONF_CAMERAS,
    CONF_ENV_SENSORS,
    CONF_EVIDENCE_PATH,
    CONF_EVIDENCE_RETENTION,
    CONF_FALLBACK_AI_TASK,
    CONF_NOTIFY,
    CONF_OCCUPANCY,
    CONF_SAVE_EVIDENCE,
    CONF_WORKDAY,
    DEFAULT_EVIDENCE_RETENTION,
    DEFAULT_SAVE_EVIDENCE,
    DOMAIN,
    EVIDENCE_FOLDER,
    HAZARDS,
    LEGACY_EVIDENCE_FOLDER,
    MAX_LEVEL,
    OCCUPANCY_COOLDOWN_MIN,
    STALE_MIN,
    STARTUP_DELAY_S,
    STORAGE_VERSION,
    TASK_NAME,
)
from .prompt import SensorReading, instructions, language, structure

_LOGGER = logging.getLogger(__name__)

TICK = timedelta(minutes=1)

# Evidence file names. The current ones follow a prefix with the entry ID.
EVIDENCE_NAME = r"\d{8}-\d{6}-(?:high|critical)-camera\d+\.jpg"
LEGACY_EVIDENCE_NAME = r"\d{8}-\d{6}-(?:high|critical)-[a-z0-9_]+\.jpg"


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def _from_iso(value: Any) -> datetime | None:
    return dt_util.parse_datetime(str(value)) if value else None


def _legacy_folder_name(entry: ConfigEntry) -> str:
    return slugify(entry.title) or entry.entry_id


def default_evidence_dir(hass: HomeAssistant) -> Path:
    """Private default folder of the evidence snapshots."""
    return Path(hass.config.path(*EVIDENCE_FOLDER))


def public_dirs(hass: HomeAssistant) -> dict[str, list[str]]:
    """Folders where evidence is not allowed, by the error they cause."""
    return {
        "evidence_path_media": list(hass.config.media_dirs.values()),
        "evidence_path_www": [hass.config.path("www")],  # served on /local without login
    }


def check_evidence_dir(folder: str | Path, public: dict[str, list[str]], create: bool) -> str | None:
    """Translation key of what is wrong with a folder (blocking: run it in the executor)."""
    path = Path(folder)
    if not path.is_absolute():
        return "evidence_path_absolute"
    try:
        resolved = path.resolve()  # follows links and ".."
        for error, forbidden in public.items():
            if any(resolved.is_relative_to(Path(root).resolve()) for root in forbidden):
                return error
        if create:
            path.mkdir(parents=True, exist_ok=True)
            with tempfile.TemporaryFile(dir=path):
                pass
    except (OSError, ValueError, RuntimeError):
        return "evidence_path_not_writable"
    return None


class HazardMonitor:
    """Analyses one area and keeps the latest result."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, version: str) -> None:
        """Initialise the monitor."""
        self.hass = hass
        self.entry = entry
        self.version = version
        conf = {**entry.data, **entry.options}

        self.cameras: list[str] = list(conf[CONF_CAMERAS])
        self.engines: list[str] = [
            engine for engine in (conf.get(CONF_AI_TASK), conf.get(CONF_FALLBACK_AI_TASK)) if engine
        ]
        self.occupancy: str | None = conf.get(CONF_OCCUPANCY) or None
        self.workday: str | None = conf.get(CONF_WORKDAY) or None
        self.env_sensors: list[str] = list(conf.get(CONF_ENV_SENSORS) or [])
        self.area_description: str = conf.get(CONF_AREA_DESCRIPTION) or ""
        self.notify_services: list[str] = list(conf.get(CONF_NOTIFY) or [])
        self.save_evidence: bool = bool(conf.get(CONF_SAVE_EVIDENCE, DEFAULT_SAVE_EVIDENCE))
        self.evidence_days: int = int(conf.get(CONF_EVIDENCE_RETENTION, DEFAULT_EVIDENCE_RETENTION))
        self.evidence_dir = Path(conf.get(CONF_EVIDENCE_PATH) or default_evidence_dir(hass))
        self.used_evidence_dirs: set[str] = set()  # still pruned after the path changes

        # Latest result
        self.levels: dict[str, int | None] = dict.fromkeys(HAZARDS)
        self.confidence: int | None = None
        self.summary: str | None = None
        self.recommendation: str | None = None
        self.action_required: bool = False
        self.deescalation_pending = False
        self.last_analysis: datetime | None = None  # last successful analysis
        self.last_attempt: datetime | None = None
        self.last_error: str | None = None
        self.last_duration: float | None = None
        self.last_engine: str | None = None
        self.alert_state = "clear"
        self.monitoring = True

        self.running = False
        self._lock = asyncio.Lock()
        self._unsubs: list[CALLBACK_TYPE] = []
        self._task: asyncio.Task | None = None
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry.entry_id}")

    # ---------------------------------------------------------------- lifecycle

    @property
    def signal(self) -> str:
        """Dispatcher signal for this entry."""
        return f"{DOMAIN}_{self.entry.entry_id}"

    async def async_load(self) -> None:
        """Restore the last result."""
        data = await self._store.async_load() or {}
        levels = data.get("levels") or {}
        self.levels = {key: levels.get(key) for key in HAZARDS}
        self.confidence = data.get("confidence")
        self.summary = data.get("summary")
        self.recommendation = data.get("recommendation")
        self.action_required = bool(data.get("action_required", False))
        self.deescalation_pending = bool(data.get("deescalation_pending", False))
        self.last_analysis = _from_iso(data.get("last_analysis"))
        self.last_attempt = _from_iso(data.get("last_attempt"))
        self.last_error = data.get("last_error")
        self.last_duration = data.get("last_duration")
        self.last_engine = data.get("last_engine")
        self.alert_state = data.get("alert_state", "clear")
        self.monitoring = bool(data.get("monitoring", True))
        self.used_evidence_dirs = set(data.get("evidence_dirs") or [])

    @callback
    def async_start(self) -> None:
        """Start the schedule once Home Assistant is running."""
        self._unsubs.append(async_track_time_interval(self.hass, self._on_tick, TICK))
        self._unsubs.append(async_track_time_change(self.hass, self._on_prune, hour=3, minute=17, second=0))
        if self.occupancy:
            self._unsubs.append(async_track_state_change_event(self.hass, [self.occupancy], self._on_occupancy))
        self._unsubs.append(async_at_started(self.hass, self._on_started))

    @callback
    def _on_started(self, _hass: HomeAssistant) -> None:
        self._unsubs.append(async_call_later(self.hass, STARTUP_DELAY_S, self._on_tick))
        self._on_prune()

    async def async_stop(self) -> None:
        """Stop listening and save."""
        while self._unsubs:
            self._unsubs.pop()()
        if self._task and not self._task.done():
            self._task.cancel()
        await self._store.async_save(self._as_storage())

    # --------------------------------------------------------------- schedule

    @property
    def max_level(self) -> int:
        """Highest stored level."""
        return max((level for level in self.levels.values() if level is not None), default=0)

    @property
    def risk_level(self) -> str | None:
        """``none`` … ``critical``, ``None`` before the first analysis."""
        if all(level is None for level in self.levels.values()):
            return None
        return level_name(self.max_level)

    def is_active(self) -> bool:
        """Occupied or working hours; always active when neither is configured."""
        if not self.occupancy and not self.workday:
            return True
        return any(
            (state := self.hass.states.get(entity_id)) is not None and state.state == STATE_ON
            for entity_id in (self.occupancy, self.workday)
            if entity_id
        )

    def next_due(self) -> datetime | None:
        """When the next periodic analysis is due (``None``: right away)."""
        if self.last_attempt is None:
            return None
        failed = self.last_error is not None
        return self.last_attempt + timedelta(minutes=cadence_minutes(self.max_level, self.is_active(), failed))

    @property
    def stale(self) -> bool:
        """No successful analysis for too long while monitoring."""
        if not self.monitoring:
            return False
        if self.last_analysis is None:
            return self.last_error is not None
        return dt_util.utcnow() - self.last_analysis > timedelta(minutes=STALE_MIN)

    @callback
    def _on_tick(self, _now: Any = None) -> None:
        if not self.monitoring or self.running:
            return
        due = self.next_due()
        if due is None or dt_util.utcnow() >= due:
            self.schedule("periodic")

    @callback
    def _on_occupancy(self, event: Event[EventStateChangedData]) -> None:
        new = event.data["new_state"]
        if not self.monitoring or self.running or new is None or new.state != STATE_ON:
            return
        if self.last_attempt and dt_util.utcnow() - self.last_attempt < timedelta(minutes=OCCUPANCY_COOLDOWN_MIN):
            return
        self.schedule("occupancy")

    @callback
    def schedule(self, reason: str) -> None:
        self._task = self.entry.async_create_background_task(
            self.hass, self.async_analyze(reason), f"{DOMAIN} analysis {self.entry.entry_id}"
        )

    async def async_set_monitoring(self, enabled: bool) -> None:
        """Pause or resume the automatic analyses."""
        self.monitoring = enabled
        self._save()
        self._notify()
        if enabled:
            self._on_tick()

    # --------------------------------------------------------------- analysis

    def _sensor_readings(self) -> list[SensorReading]:
        readings = []
        for entity_id in self.env_sensors:
            state = self.hass.states.get(entity_id)
            if state is None:
                continue
            readings.append(
                SensorReading(
                    name=state.attributes.get(ATTR_FRIENDLY_NAME) or entity_id,
                    value=state.state,
                    unit=state.attributes.get(ATTR_UNIT_OF_MEASUREMENT),
                    device_class=state.attributes.get(ATTR_DEVICE_CLASS),
                )
            )
        return readings

    def _camera_names(self) -> list[str]:
        names = []
        for entity_id in self.cameras:
            state = self.hass.states.get(entity_id)
            names.append(str(state.attributes.get(ATTR_FRIENDLY_NAME)) if state else entity_id)
        return names

    def _engine_order(self) -> list[str]:
        """Configured engines, unavailable ones last (still tried if nothing else is left)."""

        def unavailable(entity_id: str) -> bool:
            state = self.hass.states.get(entity_id)
            return state is None or state.state == STATE_UNAVAILABLE

        return sorted(self.engines, key=unavailable)

    async def _async_call_engine(self, engine: str, prompt: str) -> Any:
        """Run one AI Task call with a hard timeout and return its ``data``."""
        async with asyncio.timeout(ANALYSIS_TIMEOUT_S):
            response = await self.hass.services.async_call(
                "ai_task",
                "generate_data",
                {
                    "task_name": TASK_NAME,
                    "entity_id": engine,
                    "instructions": prompt,
                    "structure": structure(),
                    "attachments": [
                        {"media_content_id": f"media-source://camera/{entity_id}", "media_content_type": "image/jpeg"}
                        for entity_id in self.cameras
                    ],
                },
                blocking=True,
                return_response=True,
            )
        return (response or {}).get("data")

    async def async_analyze(self, reason: str = "manual") -> bool:
        """Run one analysis. Returns ``True`` on success; never raises."""
        if self._lock.locked():
            return False
        async with self._lock:
            self.running = True
            self._notify()
            started = time.monotonic()
            lang = self.hass.config.language
            _, no_action = language(lang)
            prompt = instructions(self._camera_names(), self._sensor_readings(), lang, self.area_description)
            errors: list[str] = []
            reading: Reading | None = None
            try:
                for engine in self._engine_order():
                    try:
                        reading = parse_reading(await self._async_call_engine(engine, prompt), no_action)
                    except TimeoutError:
                        errors.append(f"{engine}: no answer within {ANALYSIS_TIMEOUT_S} s")
                    except InvalidResponse as err:
                        errors.append(f"{engine}: invalid response (field '{err}')")
                    except (HomeAssistantError, vol.Invalid, ValueError, KeyError) as err:
                        errors.append(f"{engine}: {err}")
                    else:
                        self.last_engine = engine
                        break
                    _LOGGER.warning("Hazard analysis (%s) failed: %s", reason, errors[-1])
            finally:
                self.running = False
                self.last_attempt = dt_util.utcnow()
                self.last_duration = round(time.monotonic() - started, 1)

            if reading is None:
                self.last_error = "; ".join(errors) or "no AI Task entity configured"
                self._save()
                self._notify()
                return False

            self.last_error = None
            await self._async_apply(reading)
            return True

    async def _async_apply(self, reading: Reading) -> None:
        write, self.deescalation_pending = apply_hysteresis(self.max_level, reading, self.deescalation_pending)
        if write:
            self.levels = dict(reading.levels)
        self.confidence = reading.confidence
        self.summary = reading.summary
        self.recommendation = reading.recommendation
        self.action_required = reading.action_required
        self.last_analysis = self.last_attempt
        self._save()
        self._notify()

        if self.save_evidence and reading.max_level >= ALERT_LEVEL:
            await self._async_save_evidence(reading.max_level)
        await self._async_alert()

    # ----------------------------------------------------------------- alerts

    async def _async_alert(self) -> None:
        """Notify on transitions between clear, high and critical."""
        level = self.max_level
        state = "critical" if level >= MAX_LEVEL else "high" if level >= ALERT_LEVEL else "clear"
        if state == self.alert_state:
            return
        previous, self.alert_state = self.alert_state, state
        self._save()

        lang = self.hass.config.language
        name = self.entry.title
        notification_id = f"{DOMAIN}_{self.entry.entry_id}"
        if state == "clear":
            title = notify_text.text(lang, "clear_title", name=name)
            message = self.summary or notify_text.text(lang, "clear_message")
            persistent_notification.async_dismiss(self.hass, notification_id)
            if previous == "clear":
                return
        else:
            title = notify_text.text(lang, f"{state}_title", name=name)
            worst = [notify_text.text(lang, key) for key, value in self.levels.items() if value == level]
            message = f"[{', '.join(worst)}] {self.summary or ''}".strip()
            if self.action_required and self.recommendation:
                message += "\n" + notify_text.text(lang, "action", text=self.recommendation)
            persistent_notification.async_create(self.hass, message, title, notification_id)

        for service in self.notify_services:
            data: dict[str, Any] = {"tag": notification_id}
            if state != "clear" and self.cameras:
                data["image"] = f"/api/camera_proxy/{self.cameras[0]}"
            if state == "critical":
                data |= {"priority": "high", "ttl": 0, "push": {"interruption-level": "time-sensitive"}}
            try:
                await self.hass.services.async_call(
                    "notify", service.removeprefix("notify."), {"title": title, "message": message, "data": data}
                )
            except (HomeAssistantError, ValueError) as err:
                _LOGGER.warning("Hazard alert via notify.%s failed: %s", service, err)

    # --------------------------------------------------------------- evidence

    @property
    def _evidence_prefix(self) -> str:
        return f"{DOMAIN}-{self.entry.entry_id}-"

    async def _async_save_evidence(self, level: int) -> None:
        stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
        if str(self.evidence_dir) not in self.used_evidence_dirs:
            self.used_evidence_dirs.add(str(self.evidence_dir))
            self._save()
        for number, entity_id in enumerate(self.cameras, 1):
            try:
                image = await camera.async_get_image(self.hass, entity_id)
            except HomeAssistantError as err:
                _LOGGER.warning("Evidence snapshot of %s failed: %s", entity_id, err)
                continue
            # Generated name only: nothing typed by the user ends up in it.
            path = self.evidence_dir / f"{self._evidence_prefix}{stamp}-{level_name(level)}-camera{number}.jpg"
            error = await self.hass.async_add_executor_job(_write_evidence, path, image.content, public_dirs(self.hass))
            if error:
                _LOGGER.warning("Evidence snapshot of %s not saved: %s", entity_id, error)

    @callback
    def _on_prune(self, _now: datetime | None = None) -> None:
        """Delete expired snapshots, also when saving is disabled."""
        folders = {default_evidence_dir(self.hass), self.evidence_dir, *map(Path, self.used_evidence_dirs)}
        # Old media folder: every subfolder except the ones that other entries prune.
        entries = self.hass.config_entries.async_entries(DOMAIN)
        others = {_legacy_folder_name(entry) for entry in entries} - {_legacy_folder_name(self.entry)}
        media = self.hass.config.media_dirs.get("local") or self.hass.config.path("media")
        self.hass.async_add_executor_job(
            _prune_all,
            folders,
            re.compile(re.escape(self._evidence_prefix) + EVIDENCE_NAME),
            Path(media) / LEGACY_EVIDENCE_FOLDER,
            others,
            self.evidence_days,
        )

    # ---------------------------------------------------------------- storage

    def _as_storage(self) -> dict[str, Any]:
        return {
            "levels": self.levels,
            "confidence": self.confidence,
            "summary": self.summary,
            "recommendation": self.recommendation,
            "action_required": self.action_required,
            "deescalation_pending": self.deescalation_pending,
            "last_analysis": _iso(self.last_analysis),
            "last_attempt": _iso(self.last_attempt),
            "last_error": self.last_error,
            "last_duration": self.last_duration,
            "last_engine": self.last_engine,
            "alert_state": self.alert_state,
            "monitoring": self.monitoring,
            "evidence_dirs": sorted(self.used_evidence_dirs),
        }

    def diagnostics(self) -> dict[str, Any]:
        """State for the diagnostics download (no images, paths or texts of the scene)."""
        data = self._as_storage()
        data.pop("summary")
        data.pop("recommendation")
        data.pop("evidence_dirs")
        return {
            **data,
            "version": self.version,
            "running": self.running,
            "active": self.is_active(),
            "next_due": _iso(self.next_due()),
            "cameras": len(self.cameras),
            "engines": len(self.engines),
            "environment_sensors": len(self.env_sensors),
        }

    def _save(self) -> None:
        self._store.async_delay_save(self._as_storage, 5)

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, self.signal)


def _write_evidence(path: Path, content: bytes, public: dict[str, list[str]]) -> str | None:
    """Write a snapshot; return the error instead of raising, so the alert is never lost."""
    # Checked again at every write: media folders and links can change after the setup.
    if error := check_evidence_dir(path.parent, public, create=True):
        return error
    try:
        path.write_bytes(content)
    except OSError as err:
        return str(err)
    return None


def _prune_all(
    folders: Iterable[Path], name: re.Pattern[str], legacy_root: Path, legacy_skip: set[str], days: int
) -> None:
    for folder in folders:
        _prune(folder, name, days)
    try:
        legacy = [path for path in legacy_root.iterdir() if path.name not in legacy_skip and not path.is_symlink()]
    except OSError:
        return  # never created
    for folder in legacy:
        _prune(folder, re.compile(LEGACY_EVIDENCE_NAME), days)


def _prune(folder: Path, name: re.Pattern[str], days: int) -> None:
    """Delete the files of the integration older than the limit, and nothing else."""
    limit = time.time() - days * 86400
    try:
        files = [path for path in folder.iterdir() if name.fullmatch(path.name)] if folder.is_dir() else []
    except OSError as err:
        _LOGGER.warning("Evidence cleanup failed: %s", err)
        return
    for file in files:
        try:
            if file.is_file() and file.stat().st_mtime < limit:
                file.unlink(missing_ok=True)
        except OSError as err:
            _LOGGER.warning("Evidence cleanup failed: %s", err)
