"""Persistence and record log tests."""

from custom_components.pool_maintenance_tracker.const import MAX_RECORDS
from custom_components.pool_maintenance_tracker.processor import process_payload

from .conftest import SALT_OPTIONS, setup_entry


async def test_record_log_is_capped(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker

    for _ in range(MAX_RECORDS + 5):
        result = process_payload({"categories": ["other"]}, SALT_OPTIONS)
        tracker.async_apply(result)
    await hass.async_block_till_done()

    assert len(tracker.records) == MAX_RECORDS


async def test_records_survive_reload(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker
    result = process_payload({"person": "Lucas", "categories": ["filter_wash"]}, SALT_OPTIONS)
    tracker.async_apply(result)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_reload(salt_entry.entry_id)
    await hass.async_block_till_done()

    tracker = salt_entry.runtime_data.tracker
    assert len(tracker.records) == 1
    assert tracker.records[0]["person"] == "Lucas"
    assert tracker.last_record["categories"] == ["filter_wash"]
    assert tracker.get_timestamp("filter_wash") is not None
