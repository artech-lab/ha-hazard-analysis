# SPDX-License-Identifier: GPL-3.0-or-later
"""Config and options flow for Hazard Analysis."""

from __future__ import annotations

from typing import Any

from homeassistant.components.ai_task import AITaskEntityFeature
from homeassistant.config_entries import ConfigEntry, ConfigFlow, ConfigFlowResult, OptionsFlow
from homeassistant.const import ATTR_SUPPORTED_FEATURES, CONF_NAME, UnitOfTime
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import selector
import voluptuous as vol

from .const import (
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
    CONFIG_VERSION,
    DEFAULT_EVIDENCE_RETENTION,
    DEFAULT_NAME,
    DEFAULT_SAVE_EVIDENCE,
    DOMAIN,
    MAX_CAMERAS,
    MAX_EVIDENCE_RETENTION,
    MIN_EVIDENCE_RETENTION,
)
from .monitor import check_evidence_dir, default_evidence_dir, public_dirs

OPTIONAL_ENTITIES = (CONF_FALLBACK_AI_TASK, CONF_OCCUPANCY, CONF_WORKDAY)


def _ai_tasks(hass: HomeAssistant) -> list[str]:
    """AI Task entities that accept image attachments."""
    needed = AITaskEntityFeature.GENERATE_DATA | AITaskEntityFeature.SUPPORT_ATTACHMENTS
    return [
        state.entity_id
        for state in hass.states.async_all("ai_task")
        if int(state.attributes.get(ATTR_SUPPORTED_FEATURES) or 0) & needed == needed
    ]


def _suggested(current: dict[str, Any], key: str) -> dict[str, Any]:
    return {"suggested_value": current.get(key)}


def _sources(current: dict[str, Any], default_ai_task: str | None) -> dict[Any, Any]:
    """Fields shared by the setup and the options form."""
    return {
        vol.Required(CONF_CAMERAS, default=current.get(CONF_CAMERAS, [])): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="camera", multiple=True)
        ),
        vol.Required(CONF_AI_TASK, default=current.get(CONF_AI_TASK, default_ai_task)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain="ai_task")
        ),
        vol.Optional(CONF_OCCUPANCY, description=_suggested(current, CONF_OCCUPANCY)): selector.EntitySelector(
            selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean"])
        ),
        vol.Optional(CONF_AREA_DESCRIPTION, description=_suggested(current, CONF_AREA_DESCRIPTION)): (
            selector.TextSelector(selector.TextSelectorConfig(multiline=True))
        ),
    }


def _save_evidence(current: dict[str, Any]) -> dict[Any, Any]:
    default = current.get(CONF_SAVE_EVIDENCE, DEFAULT_SAVE_EVIDENCE)
    return {vol.Required(CONF_SAVE_EVIDENCE, default=default): selector.BooleanSelector()}


def _validate(user_input: dict[str, Any]) -> dict[str, str]:
    errors = {}
    if not 1 <= len(user_input.get(CONF_CAMERAS) or []) <= MAX_CAMERAS:
        errors[CONF_CAMERAS] = "camera_count"
    fallback = user_input.get(CONF_FALLBACK_AI_TASK)
    if fallback and fallback == user_input.get(CONF_AI_TASK):
        errors[CONF_FALLBACK_AI_TASK] = "same_engine"
    return errors


async def _async_check_evidence(hass: HomeAssistant, user_input: dict[str, Any]) -> str | None:
    """Check the evidence folder; it is created and written to only when saving is enabled."""
    save = user_input[CONF_SAVE_EVIDENCE]
    custom = user_input.get(CONF_EVIDENCE_PATH)
    if not save and not custom:
        return None
    folder = custom or default_evidence_dir(hass)
    return await hass.async_add_executor_job(check_evidence_dir, folder, public_dirs(hass), save)


class HazardAnalysisConfigFlow(ConfigFlow, domain=DOMAIN):
    """Initial setup: cameras and AI Task entity."""

    VERSION = CONFIG_VERSION

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Single setup form."""
        engines = _ai_tasks(self.hass)
        if not engines:
            return self.async_abort(reason="no_ai_task")

        errors: dict[str, str] = {}
        if user_input is not None:
            errors = _validate(user_input)
            if not errors and (error := await _async_check_evidence(self.hass, user_input)):
                errors[CONF_SAVE_EVIDENCE] = error  # this form has no path field
        if user_input is not None and not errors:
            return self.async_create_entry(title=user_input.pop(CONF_NAME), data=user_input)

        current = user_input or {}
        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current.get(CONF_NAME, DEFAULT_NAME)): selector.TextSelector(),
                **_sources(current, engines[0]),
                **_save_evidence(current),
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> HazardAnalysisOptionsFlow:
        """Return the options flow."""
        return HazardAnalysisOptionsFlow()


class HazardAnalysisOptionsFlow(OptionsFlow):
    """Everything except the name."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Single options form."""
        errors: dict[str, str] = {}
        if user_input is not None:
            user_input[CONF_EVIDENCE_PATH] = user_input.get(CONF_EVIDENCE_PATH, "").strip()
            user_input[CONF_EVIDENCE_RETENTION] = int(user_input[CONF_EVIDENCE_RETENTION])
            errors = _validate(user_input)
            if not errors and (error := await _async_check_evidence(self.hass, user_input)):
                errors[CONF_EVIDENCE_PATH] = error
        if user_input is not None and not errors:
            # Optional fields removed in the form must be cleared explicitly.
            for key in OPTIONAL_ENTITIES:
                user_input.setdefault(key, None)
            user_input.setdefault(CONF_AREA_DESCRIPTION, "")
            user_input.setdefault(CONF_ENV_SENSORS, [])
            user_input.setdefault(CONF_NOTIFY, [])
            return self.async_create_entry(data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options, **(user_input or {})}
        notify_services = sorted(self.hass.services.async_services_for_domain("notify"))
        notify_services = [
            service for service in notify_services if service not in {"send_message", "persistent_notification"}
        ]
        schema = vol.Schema(
            {
                **_sources(current, None),
                vol.Optional(CONF_FALLBACK_AI_TASK, description=_suggested(current, CONF_FALLBACK_AI_TASK)): (
                    selector.EntitySelector(selector.EntitySelectorConfig(domain="ai_task"))
                ),
                vol.Optional(CONF_WORKDAY, description=_suggested(current, CONF_WORKDAY)): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["binary_sensor", "input_boolean", "schedule"])
                ),
                vol.Optional(CONF_ENV_SENSORS, default=current.get(CONF_ENV_SENSORS, [])): selector.EntitySelector(
                    selector.EntitySelectorConfig(domain=["sensor", "binary_sensor"], multiple=True)
                ),
                vol.Optional(CONF_NOTIFY, default=current.get(CONF_NOTIFY, [])): selector.SelectSelector(
                    selector.SelectSelectorConfig(
                        options=notify_services,
                        multiple=True,
                        custom_value=True,
                        mode=selector.SelectSelectorMode.DROPDOWN,
                    )
                ),
                **_save_evidence(current),
                vol.Required(
                    CONF_EVIDENCE_RETENTION,
                    default=current.get(CONF_EVIDENCE_RETENTION, DEFAULT_EVIDENCE_RETENTION),
                ): selector.NumberSelector(
                    selector.NumberSelectorConfig(
                        min=MIN_EVIDENCE_RETENTION,
                        max=MAX_EVIDENCE_RETENTION,
                        step=1,
                        unit_of_measurement=UnitOfTime.DAYS,
                        mode=selector.NumberSelectorMode.BOX,
                    )
                ),
                vol.Optional(CONF_EVIDENCE_PATH, description=_suggested(current, CONF_EVIDENCE_PATH)): (
                    selector.TextSelector()
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
