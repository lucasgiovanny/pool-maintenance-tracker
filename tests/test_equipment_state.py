"""Tests for the one place that decides whether equipment is running."""

import pytest

from custom_components.pool_maintenance_tracker.const import equipment_on


@pytest.mark.parametrize(
    ("domain", "state"),
    [
        ("switch", "on"),
        ("input_boolean", "on"),
        ("binary_sensor", "on"),
        ("light", "on"),
        ("fan", "on"),
        ("schedule", "on"),
        # A thermostat names the job it is doing instead of saying "on"
        ("climate", "heat"),
        ("climate", "cool"),
        ("climate", "heat_cool"),
        ("climate", "auto"),
        ("climate", "dry"),
        ("climate", "fan_only"),
        # ...and a water heater names the programme it is running
        ("water_heater", "eco"),
        ("water_heater", "performance"),
        ("water_heater", "heat_pump"),
        ("water_heater", "high_demand"),
        ("water_heater", "gas"),
        ("water_heater", "electric"),
        ("cover", "open"),
        ("cover", "opening"),
    ],
)
def test_anything_that_is_not_off_is_running(domain, state):
    assert equipment_on(domain, state) is True


@pytest.mark.parametrize(
    ("domain", "state"),
    [
        ("switch", "off"),
        ("climate", "off"),
        ("water_heater", "off"),
        ("binary_sensor", "off"),
        ("cover", "closed"),
        ("cover", "closing"),
    ],
)
def test_the_ways_of_being_off(domain, state):
    assert equipment_on(domain, state) is False


@pytest.mark.parametrize(
    ("domain", "state"),
    [
        # A reading is neither running nor stopped, and 22.5 is not "not off"
        ("sensor", "22.5"),
        ("sensor", "0"),
        ("sensor", "unknown_mode"),
        ("input_number", "7.2"),
        # Nothing to report is not a state to report on
        ("switch", "unavailable"),
        ("climate", "unknown"),
    ],
)
def test_things_that_do_not_run_have_no_answer(domain, state):
    assert equipment_on(domain, state) is None


def test_a_sensor_that_does_speak_on_and_off_is_taken_at_its_word():
    """Some integrations expose plain on/off outside the usual domains."""
    assert equipment_on("sensor", "on") is True
    assert equipment_on("sensor", "off") is False
