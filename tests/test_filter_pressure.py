"""The filter wash alert, once a pressure gauge is linked."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.pool_maintenance_tracker.const import (
    CONF_FILTER_PRESSURE_SOURCE,
    CONF_POOL_SYSTEM_ENTITY,
    METRIC_CLEAN_PRESSURE,
    TS_FILTER_WASH,
    URL_LOG,
)

from .conftest import TEST_TOKEN, setup_entry

GAUGE = "sensor.filter_pressure"
DUE_ENTITY = "binary_sensor.piscina_filter_wash_due"
LOG_URL = URL_LOG.format(token=TEST_TOKEN)


async def setup_with_gauge(hass, entry, **options):
    hass.states.async_set("switch.pool_system", "on", {"friendly_name": "Pool system"})
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry,
        options={
            **entry.options,
            CONF_FILTER_PRESSURE_SOURCE: GAUGE,
            CONF_POOL_SYSTEM_ENTITY: "switch.pool_system",
            **options,
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def log_filter_wash(hass, client):
    response = await client.post(
        LOG_URL, json={"person": "technician", "categories": ["filter_wash"]}
    )
    assert response.status == 200
    await hass.async_block_till_done()


async def test_without_a_gauge_the_interval_still_rules(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker
    tracker.timestamps[TS_FILTER_WASH] = (dt_util.utcnow() - timedelta(days=45)).isoformat()
    tracker.async_update_listeners()
    await hass.async_block_till_done()

    state = hass.states.get(DUE_ENTITY)
    assert state.state == "on"
    assert state.attributes["criterion"] == "interval"


async def test_wash_captures_the_clean_baseline(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set(GAUGE, "0.8", {"unit_of_measurement": "bar"})
    await setup_with_gauge(hass, salt_entry)
    client = await hass_client_no_auth()

    await log_filter_wash(hass, client)

    tracker = salt_entry.runtime_data.tracker
    assert tracker.metrics[METRIC_CLEAN_PRESSURE] == 0.8
    state = hass.states.get(DUE_ENTITY)
    assert state.state == "off"
    assert state.attributes["criterion"] == "pressure"


async def test_pressure_rise_calls_for_a_wash(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set(GAUGE, "0.8", {"unit_of_measurement": "bar"})
    await setup_with_gauge(hass, salt_entry)
    client = await hass_client_no_auth()
    await log_filter_wash(hass, client)

    hass.states.async_set(GAUGE, "0.95", {"unit_of_measurement": "bar"})  # +19%, still fine
    await hass.async_block_till_done()
    assert hass.states.get(DUE_ENTITY).state == "off"

    hass.states.async_set(GAUGE, "1.05", {"unit_of_measurement": "bar"})  # +31%
    await hass.async_block_till_done()
    state = hass.states.get(DUE_ENTITY)
    assert state.state == "on"
    assert state.attributes["rise_percent"] == 31
    assert state.attributes["threshold_percent"] == 25


async def test_a_clean_filter_is_not_washed_on_a_schedule(hass, salt_entry, hass_client_no_auth):
    """The whole point: the gauge overrides the calendar in both directions."""
    hass.states.async_set(GAUGE, "0.8", {"unit_of_measurement": "bar"})
    await setup_with_gauge(hass, salt_entry)
    client = await hass_client_no_auth()
    await log_filter_wash(hass, client)

    tracker = salt_entry.runtime_data.tracker
    tracker.timestamps[TS_FILTER_WASH] = (dt_util.utcnow() - timedelta(days=90)).isoformat()
    tracker.async_update_listeners()
    await hass.async_block_till_done()

    assert hass.states.get(DUE_ENTITY).state == "off"


async def test_readings_with_the_pump_off_are_ignored(hass, salt_entry, hass_client_no_auth):
    """A stopped pump drops the gauge to zero — that means nothing."""
    hass.states.async_set(GAUGE, "0.8", {"unit_of_measurement": "bar"})
    await setup_with_gauge(hass, salt_entry)
    client = await hass_client_no_auth()
    await log_filter_wash(hass, client)

    hass.states.async_set(GAUGE, "1.2", {"unit_of_measurement": "bar"})
    await hass.async_block_till_done()
    assert hass.states.get(DUE_ENTITY).state == "on"

    hass.states.async_set("switch.pool_system", "off")
    hass.states.async_set(GAUGE, "0.0", {"unit_of_measurement": "bar"})
    await hass.async_block_till_done()
    # still on: the last verdict taken under flow is the only honest one
    assert hass.states.get(DUE_ENTITY).state == "on"


async def test_no_baseline_captured_with_the_pump_off(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set(GAUGE, "0.0", {"unit_of_measurement": "bar"})
    await setup_with_gauge(hass, salt_entry)
    hass.states.async_set("switch.pool_system", "off")
    await hass.async_block_till_done()
    client = await hass_client_no_auth()
    await log_filter_wash(hass, client)

    tracker = salt_entry.runtime_data.tracker
    assert METRIC_CLEAN_PRESSURE not in tracker.metrics
    # falls back to the interval, which a fresh wash just satisfied
    state = hass.states.get(DUE_ENTITY)
    assert state.state == "off"
    assert state.attributes["criterion"] == "interval"


async def test_baseline_survives_a_reload(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set(GAUGE, "0.8", {"unit_of_measurement": "bar"})
    await setup_with_gauge(hass, salt_entry)
    client = await hass_client_no_auth()
    await log_filter_wash(hass, client)
    await salt_entry.runtime_data.tracker.async_flush()

    await hass.config_entries.async_reload(salt_entry.entry_id)
    await hass.async_block_till_done()

    assert salt_entry.runtime_data.tracker.metrics[METRIC_CLEAN_PRESSURE] == 0.8
