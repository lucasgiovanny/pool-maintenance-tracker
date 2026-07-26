"""Tests for the page-only notes diary."""

from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.pool_maintenance_tracker.const import (
    MAX_NOTES,
    URL_LOG,
    URL_NOTE,
)

from .conftest import TEST_TOKEN, setup_entry

NOTE_URL = URL_NOTE.format(token=TEST_TOKEN)
LOG_URL = URL_LOG.format(token=TEST_TOKEN)


async def test_add_note_via_endpoint(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(
        NOTE_URL, json={"person": "Técnico", "text": "Água ligeiramente turva."}
    )
    assert response.status == 200
    body = await response.json()
    assert body["ok"] is True
    assert body["note"]["person"] == "Técnico"

    tracker = salt_entry.runtime_data.tracker
    assert len(tracker.notes) == 1
    assert tracker.notes[0]["text"] == "Água ligeiramente turva."


async def test_note_appears_in_report(hass, salt_entry, hass_client_no_auth):
    import json as json_mod
    import re

    from custom_components.pool_maintenance_tracker.const import URL_PAGE

    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    await client.post(NOTE_URL, json={"person": "Lucas", "text": "Nota de teste"})

    html = await (await client.get(URL_PAGE.format(token=TEST_TOKEN))).text()
    match = re.search(r"const CFG = (\{.*?\});\n", html, re.DOTALL)
    config = json_mod.loads(match.group(1).replace("<\\/", "</"))
    assert config["report"]["notes"][0]["text"] == "Nota de teste"
    assert config["note_endpoint"].endswith("/note")


async def test_invalid_notes_rejected(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(NOTE_URL, json={"text": "   "})
    assert response.status == 400
    response = await client.post(NOTE_URL, json={"text": "x" * 501})
    assert response.status == 400
    response = await client.post(NOTE_URL, json={})
    assert response.status == 400
    assert salt_entry.runtime_data.tracker.notes == []


async def test_note_endpoint_404_when_report_disabled(hass, salt_entry, hass_client_no_auth):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, "report_enabled": False}
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    response = await client.post(NOTE_URL, json={"text": "hello"})
    assert response.status == 404


async def test_note_with_record_via_log(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    yesterday = (dt_util.utcnow() - timedelta(days=1)).isoformat()
    response = await client.post(
        LOG_URL,
        json={
            "person": "Lucas",
            "logged_at": yesterday,
            "categories": ["filter_wash"],
            "note": "Filtro estava muito sujo.",
        },
    )
    assert response.status == 200
    assert (await response.json())["ignored"] == []

    tracker = salt_entry.runtime_data.tracker
    assert len(tracker.records) == 1
    assert len(tracker.notes) == 1
    note = tracker.notes[0]
    assert note["text"] == "Filtro estava muito sujo."
    assert note["person"] == "Lucas"
    assert note["created_at"] == yesterday
    # the note does not live inside the record
    assert "note" not in tracker.records[0]


async def test_note_only_log_submission(hass, salt_entry, hass_client_no_auth):
    from custom_components.pool_maintenance_tracker.const import EVENT_RECORD

    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    events = []
    hass.bus.async_listen(EVENT_RECORD, events.append)

    response = await client.post(LOG_URL, json={"person": "Rafa", "note": "Só uma observação."})
    assert response.status == 200
    assert (await response.json())["ok"] is True
    await hass.async_block_till_done()

    tracker = salt_entry.runtime_data.tracker
    assert tracker.records == []
    assert events == []
    assert tracker.notes[0]["person"] == "Rafa"


async def test_invalid_note_with_valid_record_is_ignored(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(LOG_URL, json={"categories": ["cleaning"], "note": "x" * 501})
    assert response.status == 200
    body = await response.json()
    assert "note" in body["ignored"]
    tracker = salt_entry.runtime_data.tracker
    assert len(tracker.records) == 1
    assert tracker.notes == []


async def test_notes_capped_and_survive_reload(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker
    for index in range(MAX_NOTES + 5):
        tracker.async_add_note("Lucas", f"nota {index}")
    assert len(tracker.notes) == MAX_NOTES
    assert tracker.notes[-1]["text"] == f"nota {MAX_NOTES + 4}"

    assert await hass.config_entries.async_reload(salt_entry.entry_id)
    await hass.async_block_till_done()
    tracker = salt_entry.runtime_data.tracker
    assert len(tracker.notes) == MAX_NOTES
