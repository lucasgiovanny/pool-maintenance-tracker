"""Setup/unload lifecycle tests."""

from homeassistant.config_entries import ConfigEntryState

from custom_components.pool_maintenance_tracker.const import (
    CONF_TOKEN,
    DATA_TOKENS,
    DOMAIN,
)

from .conftest import setup_entry


async def test_setup_and_unload(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    assert salt_entry.state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN][DATA_TOKENS][salt_entry.data[CONF_TOKEN]] == salt_entry.entry_id

    assert await hass.config_entries.async_unload(salt_entry.entry_id)
    await hass.async_block_till_done()
    assert salt_entry.state is ConfigEntryState.NOT_LOADED
    assert salt_entry.data[CONF_TOKEN] not in hass.data[DOMAIN][DATA_TOKENS]


async def test_two_entries_share_views(hass, salt_entry, chlorine_entry):
    await setup_entry(hass, salt_entry)
    await setup_entry(hass, chlorine_entry)
    tokens = hass.data[DOMAIN][DATA_TOKENS]
    assert len(tokens) == 2

    assert await hass.config_entries.async_unload(salt_entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][DATA_TOKENS]) == 1
