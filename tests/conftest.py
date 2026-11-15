"""Shared fixtures."""

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
import pytest


@pytest.fixture(autouse=True)
async def auto_enable_custom_integrations(hass: HomeAssistant, enable_custom_integrations):
    """Enable loading custom integrations in all tests.

    The ``homeassistant`` component is needed by ``conversation``, a dependency
    of ``ai_task``.
    """
    assert await async_setup_component(hass, "homeassistant", {})
    yield
