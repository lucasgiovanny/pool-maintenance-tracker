"""Tests for the wall dashboard (kiosk) page."""

import json
import re
from datetime import timedelta

from homeassistant.util import dt as dt_util

from custom_components.pool_maintenance_tracker.const import (
    URL_KIOSK,
    URL_LOG,
    URL_STATE,
)

from .conftest import TEST_TOKEN, setup_entry

KIOSK_URL = URL_KIOSK.format(token=TEST_TOKEN)


def extract_config(html: str) -> dict:
    match = re.search(r"const CFG = (\{.*?\});\n", html, re.DOTALL)
    assert match, "injected kiosk config not found"
    return json.loads(match.group(1).replace("<\\/", "</"))


async def test_kiosk_page(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(
        URL_LOG.format(token=TEST_TOKEN),
        json={"person": "Lucas", "categories": ["water_test"], "readings": {"ph": 7.2}},
    )
    assert response.status == 200
    await hass.async_block_till_done()

    response = await client.get(KIOSK_URL)
    assert response.status == 200
    assert response.headers["Cache-Control"] == "no-store"
    html = await response.text()
    assert "__KIOSK_CONFIG__" not in html

    config = extract_config(html)
    assert config["pool_name"] == "Piscina"
    assert config["language"] == "pt"
    assert config["state_endpoint"] == URL_STATE.format(token=TEST_TOKEN)
    assert config["report"]["values"]["ph"] == 7.2
    assert config["strings"]["kiosk"]["attention"] == "Precisa de atenção"
    assert config["strings"]["roles"]["heat_pump"] == "Bomba de calor"


async def test_kiosk_shows_schedule_countdown_data(hass, salt_entry, hass_client_no_auth):
    next_event = dt_util.utcnow() + timedelta(hours=2)
    hass.states.async_set(
        "schedule.filtracao",
        "off",
        {"friendly_name": "Filtração", "next_event": next_event},
    )
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "report_sensors": ["schedule.filtracao"]},
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(KIOSK_URL)).text())
    schedule = config["report"]["extra"][0]
    assert schedule["domain"] == "schedule"
    assert schedule["next_change"] == next_event.isoformat()


async def test_kiosk_disabled_returns_404(hass, salt_entry, hass_client_no_auth):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, "kiosk_enabled": False}
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    response = await client.get(KIOSK_URL)
    assert response.status == 404
    # the status tab still works, so /state stays available
    response = await client.get(URL_STATE.format(token=TEST_TOKEN))
    assert response.status == 200


async def test_state_available_for_kiosk_without_report(hass, salt_entry, hass_client_no_auth):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "report_enabled": False, "kiosk_enabled": True},
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    assert (await client.get(KIOSK_URL)).status == 200
    assert (await client.get(URL_STATE.format(token=TEST_TOKEN))).status == 200


async def test_kiosk_unknown_token_404(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.get(URL_KIOSK.format(token="nope"))
    assert response.status == 404


async def test_roles_replace_guessing(hass, salt_entry, hass_client_no_auth):
    """Role entities get a fixed place and leave the generic extra list."""
    hass.states.async_set("switch.pool_system", "on", {"friendly_name": "Pool System"})
    hass.states.async_set("switch.heat_pump", "off", {"friendly_name": "Eco Elyo"})
    hass.states.async_set(
        "sensor.power", "1.2", {"friendly_name": "Consumo", "unit_of_measurement": "kW"}
    )
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={
            **salt_entry.options,
            "pool_system_entity": "switch.pool_system",
            "heat_pump_entity": "switch.heat_pump",
            # also listed as an extra entity: must not be duplicated
            "report_sensors": ["switch.pool_system", "sensor.power"],
        },
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(KIOSK_URL)).text())
    roles = config["report"]["roles"]
    assert roles["pool_system"]["state"] == "on"
    assert roles["heat_pump"]["name"] == "Eco Elyo"
    extra_ids = [item["entity_id"] for item in config["report"]["extra"]]
    assert extra_ids == ["sensor.power"]


async def test_running_equipment_never_says_on(hass, salt_entry, hass_client_no_auth):
    """A heat pump that is heating is running, whatever word it uses for it.

    A thermostat reports its mode — "heat", "eco" — and never the word "on",
    so a dashboard comparing against "on" calls a working heat pump idle.
    """
    hass.states.async_set("climate.heat_pump", "heat", {"friendly_name": "Eco Elyo"})
    hass.states.async_set("switch.pool_system", "on", {"friendly_name": "Pool System"})
    hass.states.async_set("cover.pool", "open", {"friendly_name": "Cover"})
    hass.states.async_set(
        "sensor.power", "22.5", {"friendly_name": "Consumo", "unit_of_measurement": "kW"}
    )
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={
            **salt_entry.options,
            "heat_pump_entity": "climate.heat_pump",
            "pool_system_entity": "switch.pool_system",
            "cover_entity": "cover.pool",
            "report_sensors": ["sensor.power"],
        },
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    report = extract_config(await (await client.get(KIOSK_URL)).text())["report"]
    assert report["roles"]["heat_pump"]["on"] is True
    assert report["roles"]["pool_system"]["on"] is True
    assert report["roles"]["cover"]["on"] is True
    # A reading is not equipment: it is neither running nor stopped.
    assert report["extra"][0]["on"] is None

    # The same pump, off, is off — including the modes that mean standby.
    for mode in ("off", "closed"):
        hass.states.async_set("climate.heat_pump", mode, {"friendly_name": "Eco Elyo"})
        await hass.async_block_till_done()
        report = extract_config(await (await client.get(KIOSK_URL)).text())["report"]
        assert report["roles"]["heat_pump"]["on"] is False
