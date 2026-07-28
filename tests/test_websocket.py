"""Tests for the WebSocket API behind the Lovelace card."""

from custom_components.pool_maintenance_tracker.const import DOMAIN, URL_LOG

from .conftest import TEST_TOKEN, setup_entry


async def test_pools_and_status(hass, salt_entry, hass_ws_client, hass_client_no_auth):
    hass.states.async_set("switch.pool_system", "on", {"friendly_name": "Pool System"})
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "pool_system_entity": "switch.pool_system"},
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()

    http = await hass_client_no_auth()
    await http.post(
        URL_LOG.format(token=TEST_TOKEN),
        json={"person": "Lucas", "categories": ["filter_wash"], "readings": {"ph": 7.4}},
    )
    await hass.async_block_till_done()

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/pools"})
    result = await client.receive_json()
    assert result["success"]
    assert result["result"][0]["entry_id"] == salt_entry.entry_id
    assert result["result"][0]["title"] == "Piscina"

    await client.send_json({"id": 2, "type": f"{DOMAIN}/status", "entry_id": salt_entry.entry_id})
    result = await client.receive_json()
    assert result["success"]
    data = result["result"]
    assert data["title"] == "Piscina"
    assert data["report"]["values"]["ph"] == 7.4
    assert data["report"]["roles"]["pool_system"]["state"] == "on"
    # entity ids let the card open more-info dialogs
    assert data["report"]["entity_ids"]["ph"].startswith("number.")
    assert data["strings"]["tabs"]["log"]


async def test_status_unknown_entry(hass, salt_entry, hass_ws_client):
    await setup_entry(hass, salt_entry)
    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/status", "entry_id": "does-not-exist"})
    result = await client.receive_json()
    assert not result["success"]
    assert result["error"]["code"] == "not_found"
