"""Common fixtures for Pool Maintenance Tracker tests."""

from __future__ import annotations

import pytest
from homeassistant.const import CONF_NAME
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.pool_maintenance_tracker.const import (
    CONF_CELL_DAYS,
    CONF_FILTER_DAYS,
    CONF_LANGUAGE,
    CONF_MODULES,
    CONF_NOTIFY_SERVICE,
    CONF_POOL_TYPE,
    CONF_PROBE_DAYS,
    CONF_REMINDER_TIME,
    CONF_TOKEN,
    DOMAIN,
    POOL_TYPE_CHLORINE,
    POOL_TYPE_SALT,
)

TEST_TOKEN = "test-token-abcdefghijklmnopqrstuvwxyz012345"

SALT_OPTIONS = {
    CONF_POOL_TYPE: POOL_TYPE_SALT,
    CONF_MODULES: ["salt_chlorinator", "acid_tank", "filter", "ph_probe", "cleaning"],
    CONF_LANGUAGE: "pt",
    CONF_NOTIFY_SERVICE: "notify.test_target",
    CONF_FILTER_DAYS: 30,
    CONF_PROBE_DAYS: 60,
    CONF_CELL_DAYS: 90,
    CONF_REMINDER_TIME: "10:00",
}

CHLORINE_OPTIONS = {
    CONF_POOL_TYPE: POOL_TYPE_CHLORINE,
    CONF_MODULES: ["filter", "cleaning"],
    CONF_LANGUAGE: "en",
    CONF_NOTIFY_SERVICE: "",
    CONF_FILTER_DAYS: 30,
    CONF_REMINDER_TIME: "10:00",
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom integrations in all tests."""
    return


@pytest.fixture
def salt_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Piscina",
        data={CONF_NAME: "Piscina", CONF_TOKEN: TEST_TOKEN},
        options=dict(SALT_OPTIONS),
    )


@pytest.fixture
def chlorine_entry() -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        title="Backyard pool",
        data={CONF_NAME: "Backyard pool", CONF_TOKEN: "another-token-0123456789abcdef"},
        options=dict(CHLORINE_OPTIONS),
    )


async def setup_entry(hass, entry: MockConfigEntry) -> None:
    """Add an entry to hass and set it up."""
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
