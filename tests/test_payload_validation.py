"""Pure-logic tests for payload v2 validation."""

from datetime import timedelta

import pytest
from homeassistant.util import dt as dt_util

from custom_components.pool_maintenance_tracker.processor import (
    PayloadError,
    process_payload,
)

from .conftest import CHLORINE_OPTIONS, SALT_OPTIONS

NOW = dt_util.utcnow()


def test_full_valid_payload():
    result = process_payload(
        {
            "version": 2,
            "person": "Lucas",
            "logged_at": NOW.isoformat(),
            "categories": ["water_test", "filter_wash", "cell_clean"],
            "readings": {"ph": 7.2, "free_chlorine": 1.5, "salt": 3.0},
            "chlorinator": {"output": 5, "mode": "smart"},
            "salt": {"added_kg": 25},
            "acid": {"level": "half"},
            "cleaning": {"types": ["vacuum"]},
        },
        SALT_OPTIONS,
        now=NOW,
    )
    assert result.ignored == []
    assert result.values["ph"] == 7.2
    assert result.values["free_chlorine"] == 1.5
    assert result.values["salt_level"] == 3.0
    assert result.values["salt_added"] == 25
    assert result.values["chlorinator_output"] == 5
    assert result.values["chlorinator_mode"] == "smart"
    assert result.values["acid_tank_level"] == "half"
    assert result.values["cleaning_types"] == ["vacuum"]
    assert result.record["person"] == "Lucas"
    assert result.record["categories"] == ["water_test", "filter_wash", "cell_clean"]
    # timestamps: categories + implied by data
    assert set(result.timestamps) == {
        "any",
        "water_test",
        "filter_wash",
        "cell_clean",
        "acid_refill",
        "cleaning",
    }


def test_out_of_range_values_are_ignored_not_fatal():
    result = process_payload(
        {"person": "Rafa", "readings": {"ph": 11.0, "free_chlorine": 2.0}},
        SALT_OPTIONS,
        now=NOW,
    )
    assert "readings.ph" in result.ignored
    assert "ph" not in result.values
    assert result.values["free_chlorine"] == 2.0


def test_booleans_are_not_numbers():
    result = process_payload(
        {"readings": {"ph": True, "free_chlorine": 1.0}}, SALT_OPTIONS, now=NOW
    )
    assert "readings.ph" in result.ignored
    assert "ph" not in result.values


def test_null_fields_are_noops():
    result = process_payload(
        {
            "person": "Lucas",
            "categories": ["filter_wash"],
            "readings": {"ph": None, "free_chlorine": None, "salt": None},
            "chlorinator": {"output": None, "mode": None},
            "acid": {"level": None},
        },
        SALT_OPTIONS,
        now=NOW,
    )
    assert result.ignored == []
    assert result.values == {}
    assert result.record["categories"] == ["filter_wash"]


def test_empty_payload_rejected():
    with pytest.raises(PayloadError):
        process_payload({}, SALT_OPTIONS, now=NOW)


def test_only_invalid_content_rejected():
    with pytest.raises(PayloadError):
        process_payload({"person": "X", "readings": {"ph": 99}}, SALT_OPTIONS, now=NOW)


def test_non_dict_rejected():
    with pytest.raises(PayloadError):
        process_payload([1, 2, 3], SALT_OPTIONS, now=NOW)


def test_disabled_module_sections_ignored():
    result = process_payload(
        {
            "categories": ["water_test", "chlorinator"],
            "readings": {"ph": 7.0, "salt": 3.0},
            "chlorinator": {"output": 5, "mode": "boost"},
            "acid": {"level": "full"},
        },
        CHLORINE_OPTIONS,
        now=NOW,
    )
    # chlorinator category and sections are not available on a chlorine pool
    assert result.record["categories"] == ["water_test"]
    assert "chlorinator.output" in result.ignored
    assert "chlorinator.mode" in result.ignored
    assert "readings.salt" in result.ignored
    assert "acid.level" in result.ignored
    assert "categories.chlorinator" in result.ignored
    assert result.values == {"ph": 7.0}


def test_invalid_enum_ignored():
    result = process_payload(
        {"categories": ["cleaning"], "chlorinator": {"mode": "turbo"}},
        SALT_OPTIONS,
        now=NOW,
    )
    assert "chlorinator.mode" in result.ignored
    assert "chlorinator_mode" not in result.values


def test_cleaning_types_filtered():
    result = process_payload({"cleaning": {"types": ["vacuum", "lasers"]}}, SALT_OPTIONS, now=NOW)
    assert result.values["cleaning_types"] == ["vacuum"]
    assert "cleaning.types.lasers" in result.ignored


def test_logged_at_out_of_window_uses_server_time():
    stale = (NOW - timedelta(days=30)).isoformat()
    result = process_payload(
        {"categories": ["cleaning"], "logged_at": stale}, SALT_OPTIONS, now=NOW
    )
    assert result.record["logged_at"] == NOW.isoformat()


def test_logged_at_recent_is_kept():
    recent = (NOW - timedelta(hours=2)).isoformat()
    result = process_payload(
        {"categories": ["cleaning"], "logged_at": recent}, SALT_OPTIONS, now=NOW
    )
    assert result.record["logged_at"] == recent


def test_person_too_long_becomes_unknown():
    result = process_payload(
        {"person": "x" * 50, "categories": ["cleaning"]}, SALT_OPTIONS, now=NOW
    )
    assert result.record["person"] == "unknown"
    assert "person" in result.ignored


def test_unknown_top_level_keys_ignored_silently():
    result = process_payload({"categories": ["cleaning"], "hack": {"a": 1}}, SALT_OPTIONS, now=NOW)
    assert result.record["categories"] == ["cleaning"]
