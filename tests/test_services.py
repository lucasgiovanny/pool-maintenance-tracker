"""Tests for the delete_record service."""

import pytest
from homeassistant.exceptions import ServiceValidationError

from custom_components.pool_maintenance_tracker.const import DOMAIN
from custom_components.pool_maintenance_tracker.processor import process_payload

from .conftest import SALT_OPTIONS, setup_entry


def apply_record(tracker, payload):
    result = process_payload(payload, SALT_OPTIONS)
    tracker.async_apply(result)
    return result.record


async def test_delete_last_record_rebuilds_timestamps(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker

    apply_record(tracker, {"person": "Lucas", "categories": ["cleaning"]})
    apply_record(tracker, {"person": "Rafa", "categories": ["filter_wash"]})
    assert tracker.timestamps.get("filter_wash")

    await hass.services.async_call(
        DOMAIN,
        "delete_record",
        {"config_entry": salt_entry.entry_id},
        blocking=True,
    )
    assert len(tracker.records) == 1
    # the mistaken filter wash no longer counts
    assert "filter_wash" not in tracker.timestamps
    assert tracker.timestamps.get("cleaning")
    assert tracker.last_record["person"] == "Lucas"


async def test_delete_record_by_id(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker

    first = apply_record(tracker, {"person": "Lucas", "categories": ["cleaning"]})
    apply_record(tracker, {"person": "Rafa", "categories": ["filter_wash"]})

    await hass.services.async_call(
        DOMAIN,
        "delete_record",
        {"config_entry": salt_entry.entry_id, "record_id": first["id"]},
        blocking=True,
    )
    assert len(tracker.records) == 1
    assert tracker.records[0]["person"] == "Rafa"
    assert "cleaning" not in tracker.timestamps
    assert tracker.timestamps.get("filter_wash")


async def test_delete_record_errors(hass, salt_entry):
    await setup_entry(hass, salt_entry)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "delete_record",
            {"config_entry": salt_entry.entry_id},
            blocking=True,
        )
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "delete_record",
            {"config_entry": "not-an-entry"},
            blocking=True,
        )

    apply_record(salt_entry.runtime_data.tracker, {"person": "L", "categories": ["cleaning"]})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "delete_record",
            {"config_entry": salt_entry.entry_id, "record_id": "nope"},
            blocking=True,
        )
