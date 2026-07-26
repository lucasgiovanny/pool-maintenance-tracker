"""Tests for the public POST endpoint."""

import json

from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    DOMAIN,
    EVENT_RECORD,
    URL_LOG,
)

from .conftest import TEST_TOKEN, setup_entry

LOG_URL = URL_LOG.format(token=TEST_TOKEN)


def entity_id_for(hass, platform, entry, key):
    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(platform, DOMAIN, f"{entry.entry_id}_{key}")
    assert entity_id, f"no {platform} entity for key {key}"
    return entity_id


async def test_valid_post_updates_entities(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    events = []
    hass.bus.async_listen(EVENT_RECORD, events.append)

    response = await client.post(
        LOG_URL,
        json={
            "version": 2,
            "person": "Lucas",
            "categories": ["water_test", "filter_wash"],
            "readings": {"ph": 7.4, "free_chlorine": 1.5},
            "acid": {"level": "half"},
        },
    )
    assert response.status == 200
    body = await response.json()
    assert body["ok"] is True
    assert body["ignored"] == []
    await hass.async_block_till_done()

    ph_entity = entity_id_for(hass, "number", salt_entry, "ph")
    assert hass.states.get(ph_entity).state == "7.4"

    filter_entity = entity_id_for(hass, "sensor", salt_entry, "last_filter_wash")
    assert hass.states.get(filter_entity).state != "unknown"

    record_entity = entity_id_for(hass, "sensor", salt_entry, "last_record")
    state = hass.states.get(record_entity)
    assert state.state.startswith("Lucas ·")
    assert state.attributes["categories"] == ["water_test", "filter_wash"]

    acid_entity = entity_id_for(hass, "select", salt_entry, "acid_tank_level")
    assert hass.states.get(acid_entity).state == "half"

    assert len(events) == 1
    assert events[0].data["person"] == "Lucas"
    assert events[0].data["pool_name"] == "Piscina"

    tracker = salt_entry.runtime_data.tracker
    assert len(tracker.records) == 1


async def test_event_entity_fires(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    event_entity = entity_id_for(hass, "event", salt_entry, "maintenance_logged")
    assert hass.states.get(event_entity).state == "unknown"

    response = await client.post(LOG_URL, json={"categories": ["cleaning"]})
    assert response.status == 200
    await hass.async_block_till_done()

    state = hass.states.get(event_entity)
    assert state.state != "unknown"
    assert state.attributes["event_type"] == "logged"


async def test_unknown_token_404(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.post(
        URL_LOG.format(token="wrong-token"), json={"categories": ["cleaning"]}
    )
    assert response.status == 404


async def test_invalid_json_400(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.post(
        LOG_URL, data=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status == 400
    assert (await response.json())["error"] == "invalid_json"


async def test_wrong_content_type_400(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.post(
        LOG_URL,
        data=json.dumps({"categories": ["cleaning"]}),
        headers={"Content-Type": "text/plain"},
    )
    assert response.status == 400


async def test_empty_payload_400(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.post(LOG_URL, json={})
    assert response.status == 400
    assert (await response.json())["error"] == "invalid_payload"


async def test_backdated_salt_gets_correct_timestamp(hass, salt_entry, hass_client_no_auth):
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    yesterday = (dt_util.utcnow() - timedelta(days=1)).isoformat()
    response = await client.post(
        LOG_URL,
        json={
            "categories": ["salt"],
            "salt": {"added_kg": 100},
            "logged_at": yesterday,
        },
    )
    assert response.status == 200
    await hass.async_block_till_done()

    tracker = salt_entry.runtime_data.tracker
    assert tracker.timestamps["salt_added"] == yesterday
    assert tracker.timestamps["any"] == yesterday
    assert tracker.values["salt_added"] == 100


async def test_record_snapshot_from_linked_sensors(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set("sensor.probe_ph", "7.05")
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "ph_source": "sensor.probe_ph"},
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    response = await client.post(
        LOG_URL, json={"categories": ["water_test"], "readings": {"ph": 7.2}}
    )
    assert response.status == 200
    await hass.async_block_till_done()

    record = salt_entry.runtime_data.tracker.last_record
    assert record["snapshot"] == {"ph": 7.05}


async def test_fill_on_record_mode(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set("sensor.probe_ph", "7.05")
    hass.states.async_set("sensor.probe_temp", "26.8")
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={
            **salt_entry.options,
            "ph_source": "sensor.probe_ph",
            "temperature_source": "sensor.probe_temp",
            "linked_mode": "fill_on_record",
        },
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    # manual pH wins; temperature (not measured) is filled from the probe
    response = await client.post(
        LOG_URL, json={"categories": ["water_test"], "readings": {"ph": 7.4}}
    )
    assert response.status == 200
    await hass.async_block_till_done()

    tracker = salt_entry.runtime_data.tracker
    assert tracker.values["ph"] == 7.4
    assert tracker.values["water_temperature"] == 26.8


async def test_mirror_mode_follows_sensor(hass, salt_entry):
    hass.states.async_set("sensor.probe_temp", "25.0")
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={
            **salt_entry.options,
            "temperature_source": "sensor.probe_temp",
            "linked_mode": "mirror",
        },
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()

    tracker = salt_entry.runtime_data.tracker
    # initial sync on setup
    assert tracker.values["water_temperature"] == 25.0

    hass.states.async_set("sensor.probe_temp", "26.3")
    await hass.async_block_till_done()
    assert tracker.values["water_temperature"] == 26.3

    # out-of-range and non-numeric states are ignored
    hass.states.async_set("sensor.probe_temp", "99")
    await hass.async_block_till_done()
    assert tracker.values["water_temperature"] == 26.3
    hass.states.async_set("sensor.probe_temp", "unavailable")
    await hass.async_block_till_done()
    assert tracker.values["water_temperature"] == 26.3


async def test_acid_alert_notification(hass, salt_entry, hass_client_no_auth):
    notifications = []

    async def record_notify(call):
        notifications.append(call.data)

    hass.services.async_register("notify", "test_target", record_notify)

    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(LOG_URL, json={"acid": {"level": "quarter"}})
    assert response.status == 200
    await hass.async_block_till_done()
    assert len(notifications) == 1
    assert "1/4" in notifications[0]["message"]

    # posting quarter again does not re-alert
    response = await client.post(LOG_URL, json={"acid": {"level": "quarter"}})
    assert response.status == 200
    await hass.async_block_till_done()
    assert len(notifications) == 1
