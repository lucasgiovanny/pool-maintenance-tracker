"""Tests for the history endpoint and on-time bucketing."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.pool_maintenance_tracker.const import URL_HISTORY, URL_LOG
from custom_components.pool_maintenance_tracker.http import _ontime_buckets

from .conftest import TEST_TOKEN, setup_entry

HISTORY_URL = URL_HISTORY.format(token=TEST_TOKEN)


def test_ontime_buckets_splits_days():
    now = dt_util.utcnow()
    start_local = dt_util.as_local(now).replace(hour=0, minute=0, second=0, microsecond=0)
    start = dt_util.as_utc(start_local)
    end = start + timedelta(days=2)

    # on from 22:00 day 1 until 02:00 day 2 -> 2h on each day
    changes = [
        (start, "off"),
        (start + timedelta(hours=22), "on"),
        (start + timedelta(hours=26), "off"),
    ]
    points = _ontime_buckets(changes, start, end)
    assert len(points) >= 2
    assert points[0]["v"] == 2.0
    assert points[1]["v"] == 2.0


def test_state_began_skips_unavailable_gaps():
    from custom_components.pool_maintenance_tracker.http import _state_began

    now = dt_util.utcnow()
    rows = [
        ("on", now - timedelta(days=3)),
        ("off", now - timedelta(days=2)),
        ("unavailable", now - timedelta(hours=10)),  # restart gap
        ("off", now - timedelta(hours=9, minutes=59)),
        ("unavailable", now - timedelta(minutes=2)),  # another restart
        ("off", now - timedelta(minutes=1)),
    ]
    # "off" really began 2 days ago, not at the last restart
    assert _state_began(rows, "off") == now - timedelta(days=2)
    # a state never present falls back to None
    assert _state_began(rows, "heat") is None
    # rows ending in a different state -> current state began at newest run
    rows.append(("on", now))
    assert _state_began(rows, "on") == now


def test_ontime_buckets_all_off():
    now = dt_util.utcnow()
    start = now - timedelta(days=1)
    points = _ontime_buckets([(start, "off")], start, now)
    assert all(point["v"] == 0 for point in points)


async def test_history_endpoint_manual_readings(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(
        URL_LOG.format(token=TEST_TOKEN),
        json={"person": "Lucas", "categories": ["water_test"], "readings": {"ph": 7.3}},
    )
    assert response.status == 200
    await hass.async_block_till_done()

    response = await client.get(HISTORY_URL + "?days=7")
    assert response.status == 200
    data = await response.json()
    assert data["days"] == 7
    manual = data["readings"]["ph"]["manual"]
    assert manual[0]["v"] == 7.3
    # no recorder in this test instance -> no sensor series, no extra
    assert "sensor" not in data["readings"]["ph"]
    assert data["extra"] == []


async def test_history_invalid_period(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.get(HISTORY_URL + "?days=13")
    assert response.status == 400
    response = await client.get(HISTORY_URL + "?days=abc")
    assert response.status == 400


async def test_history_gating(hass, salt_entry, hass_client_no_auth):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, "report_enabled": False}
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    response = await client.get(HISTORY_URL + "?days=7")
    assert response.status == 404
    response = await client.get(URL_HISTORY.format(token="wrong") + "?days=7")
    assert response.status == 404
