"""Entity platform tests."""

from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import DOMAIN
from custom_components.pool_maintenance_tracker.modules import active_entity_keys

from .conftest import setup_entry


def unique_keys(hass, entry):
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    return {
        item.unique_id.removeprefix(prefix)
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
    }


async def test_salt_pool_creates_all_entities(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    assert unique_keys(hass, salt_entry) == active_entity_keys(salt_entry.options)


async def test_chlorine_pool_creates_reduced_set(hass, chlorine_entry):
    await setup_entry(hass, chlorine_entry)
    keys = unique_keys(hass, chlorine_entry)
    assert keys == active_entity_keys(chlorine_entry.options)
    assert "chlorinator_mode" not in keys
    assert "salt_added" not in keys
    assert "cell_clean_due" not in keys


async def test_number_set_value_writes_through_tracker(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    registry = er.async_get(hass)
    ph_entity = registry.async_get_entity_id("number", DOMAIN, f"{salt_entry.entry_id}_ph")
    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": ph_entity, "value": 7.8},
        blocking=True,
    )
    assert salt_entry.runtime_data.tracker.values["ph"] == 7.8
    assert hass.states.get(ph_entity).state == "7.8"


async def test_select_option_writes_through_tracker(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    registry = er.async_get(hass)
    mode_entity = registry.async_get_entity_id(
        "select", DOMAIN, f"{salt_entry.entry_id}_chlorinator_mode"
    )
    await hass.services.async_call(
        "select",
        "select_option",
        {"entity_id": mode_entity, "option": "boost"},
        blocking=True,
    )
    assert salt_entry.runtime_data.tracker.values["chlorinator_mode"] == "boost"


async def test_state_survives_reload(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker
    tracker.async_set_value("ph", 7.1)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(salt_entry.entry_id)
    await hass.async_block_till_done()

    new_tracker = salt_entry.runtime_data.tracker
    assert new_tracker is not tracker
    assert new_tracker.values["ph"] == 7.1
