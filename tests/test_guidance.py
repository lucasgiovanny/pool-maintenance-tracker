"""Ideal bands, pool volume and the filtration suggestion.

These three feed every surface (page, kiosk, card) from the same payload,
so the tests here work on the page config and the /state endpoint.
"""

import json
import re

from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    CONF_FILTRATION_SCHEDULE_ENTITY,
    CONF_POOL_VOLUME,
    CONF_SALT_TARGET_MAX,
    CONF_SALT_TARGET_MIN,
    CONF_TEMPERATURE_SOURCE,
    KEY_FREE_CHLORINE,
    KEY_PH,
    KEY_SALT_LEVEL,
    URL_PAGE,
    URL_STATE,
)

from .conftest import TEST_TOKEN, setup_entry

PAGE_URL = URL_PAGE.format(token=TEST_TOKEN)
STATE_URL = URL_STATE.format(token=TEST_TOKEN)


def extract_config(html: str) -> dict:
    match = re.search(r"const CFG = (\{.*?\});\n", html, re.DOTALL)
    assert match, "injected config not found"
    return json.loads(match.group(1).replace("<\\/", "</"))


async def setup_with_options(hass, entry, **options) -> None:
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(entry, options={**entry.options, **options})
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_default_ranges(hass, salt_entry, hass_client_no_auth):
    """pH and chlorine bands are universal; salt falls back to the default."""
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    ranges = config["report"]["ranges"]
    assert ranges[KEY_PH] == {"min": 7.2, "max": 7.6}
    assert ranges[KEY_FREE_CHLORINE] == {"min": 1.0, "max": 3.0}
    assert ranges[KEY_SALT_LEVEL] == {"min": 2.5, "max": 4.5}
    assert config["report"]["volume"] is None


async def test_configured_salt_band_and_volume(hass, salt_entry, hass_client_no_auth):
    """The chlorinator decides the salt band, so it is configurable."""
    await setup_with_options(
        hass,
        salt_entry,
        **{CONF_SALT_TARGET_MIN: 3.0, CONF_SALT_TARGET_MAX: 5.0, CONF_POOL_VOLUME: 48},
    )
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["report"]["ranges"][KEY_SALT_LEVEL] == {"min": 3.0, "max": 5.0}
    assert config["report"]["volume"] == 48
    # the page needs the volume next to the salt stepper to size a dose
    assert config["strings"]["impact_salt"]

    state = await (await client.get(STATE_URL)).json()
    assert state["report"]["ranges"][KEY_SALT_LEVEL] == {"min": 3.0, "max": 5.0}
    assert state["report"]["volume"] == 48


async def test_no_filtration_hint_without_temperature(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["report"]["filtration"] is None


async def test_filtration_hint_from_linked_probe(hass, salt_entry, hass_client_no_auth):
    """Half the water temperature, rounded to the half hour."""
    hass.states.async_set(
        "sensor.probe_temperature",
        "27.4",
        {"friendly_name": "Água", "unit_of_measurement": "°C"},
    )
    await setup_with_options(
        hass, salt_entry, **{CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature"}
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["temperature"] == 27.4
    assert hint["recommended_hours"] == 13.5
    assert hint["scheduled_hours"] is None  # no schedule configured


async def test_filtration_hint_floor_and_ceiling(hass, salt_entry, hass_client_no_auth):
    """Cold water still needs a couple of hours a day."""
    hass.states.async_set("sensor.probe_temperature", "3", {"unit_of_measurement": "°C"})
    await setup_with_options(
        hass, salt_entry, **{CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature"}
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["recommended_hours"] == 2.0


async def test_filtration_hint_compares_with_schedule(
    hass, salt_entry, hass_client_no_auth, hass_storage, freezer
):
    """The suggestion sits next to what the schedule actually runs today."""
    freezer.move_to("2026-07-27 09:00:00+00:00")  # a Monday
    hass_storage["schedule"] = {
        "version": 1,
        "minor_version": 1,
        "key": "schedule",
        "data": {
            "items": [
                {
                    "id": "abc123",
                    "name": "Filtração",
                    "monday": [
                        {"from": "08:00:00", "to": "12:00:00"},
                        {"from": "15:00:00", "to": "17:30:00"},
                    ],
                }
            ]
        },
    }
    registry = er.async_get(hass)
    reg_entry = registry.async_get_or_create(
        "schedule", "schedule", "abc123", suggested_object_id="filtracao"
    )
    hass.states.async_set(reg_entry.entity_id, "on", {"friendly_name": "Filtração"})
    hass.states.async_set("sensor.probe_temperature", "24", {"unit_of_measurement": "°C"})

    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_FILTRATION_SCHEDULE_ENTITY: reg_entry.entity_id,
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["recommended_hours"] == 12.0
    assert hint["scheduled_hours"] == 6.5


async def test_filtration_hint_falls_back_to_logged_temperature(
    hass, salt_entry, hass_client_no_auth
):
    """Without a probe, the last manually logged reading is enough."""
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    await client.post(
        f"/api/pool_maintenance_tracker/{TEST_TOKEN}/log",
        json={
            "person": "technician",
            "categories": ["water_test"],
            "readings": {"ph": 7.4, "temperature": 26.0},
        },
    )
    await hass.async_block_till_done()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["temperature"] == 26.0
    assert hint["recommended_hours"] == 13.0
