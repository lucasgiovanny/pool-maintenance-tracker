"""The strip-chemistry readings: TA, CYA, hardness, total/combined chlorine."""

import json
import re
from datetime import timedelta

from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from custom_components.pool_maintenance_tracker.const import (
    DOMAIN,
    KEY_CALCIUM_HARDNESS,
    KEY_COMBINED_CHLORINE,
    KEY_CYANURIC_ACID,
    KEY_FREE_CHLORINE,
    KEY_TOTAL_ALKALINITY,
    KEY_TOTAL_CHLORINE,
    URL_LOG,
    URL_PAGE,
    URL_STATE,
)
from custom_components.pool_maintenance_tracker.modules import active_entity_keys
from custom_components.pool_maintenance_tracker.processor import process_payload

from .conftest import CHLORINE_OPTIONS, SALT_OPTIONS, TEST_TOKEN, setup_entry

NOW = dt_util.utcnow()
PAGE_URL = URL_PAGE.format(token=TEST_TOKEN)
STATE_URL = URL_STATE.format(token=TEST_TOKEN)
LOG_URL = URL_LOG.format(token=TEST_TOKEN)


def extract_config(html: str) -> dict:
    match = re.search(r"const CFG = (\{.*?\});\n", html, re.DOTALL)
    assert match, "injected config not found"
    return json.loads(match.group(1).replace("<\\/", "</"))


def test_payload_accepts_the_strip_readings():
    result = process_payload(
        {
            "person": "Lucas",
            "categories": ["water_test"],
            "readings": {
                "total_chlorine": 2.0,
                "total_alkalinity": 90,
                "cyanuric_acid": 65,
                "calcium_hardness": 250,
            },
        },
        SALT_OPTIONS,
        now=NOW,
    )
    assert result.ignored == []
    assert result.values[KEY_TOTAL_CHLORINE] == 2.0
    assert result.values[KEY_TOTAL_ALKALINITY] == 90
    assert result.values[KEY_CYANURIC_ACID] == 65
    assert result.values[KEY_CALCIUM_HARDNESS] == 250
    # The slow readings refresh their own clock, on top of the water test's
    assert "water_test" in result.timestamps
    assert "chemistry_test" in result.timestamps


def test_alkalinity_alone_is_a_water_test_not_a_chemistry_test():
    result = process_payload({"readings": {"total_alkalinity": 100}}, SALT_OPTIONS, now=NOW)
    assert "water_test" in result.timestamps
    assert "chemistry_test" not in result.timestamps


def test_chemistry_module_gates_its_readings_but_not_alkalinity():
    # CHLORINE_OPTIONS has no water_chemistry module; alkalinity is always-on
    result = process_payload(
        {
            "readings": {
                "total_alkalinity": 100,
                "total_chlorine": 2.0,
                "cyanuric_acid": 40,
                "calcium_hardness": 250,
            }
        },
        CHLORINE_OPTIONS,
        now=NOW,
    )
    assert result.values == {KEY_TOTAL_ALKALINITY: 100}
    assert "readings.total_chlorine" in result.ignored
    assert "readings.cyanuric_acid" in result.ignored
    assert "readings.calcium_hardness" in result.ignored


def test_out_of_range_chemistry_ignored():
    result = process_payload(
        {"readings": {"total_alkalinity": 900, "cyanuric_acid": 65}},
        SALT_OPTIONS,
        now=NOW,
    )
    assert "readings.total_alkalinity" in result.ignored
    assert result.values == {KEY_CYANURIC_ACID: 65}


def test_combined_chlorine_entity_follows_the_module():
    assert KEY_COMBINED_CHLORINE in active_entity_keys(SALT_OPTIONS)
    assert KEY_COMBINED_CHLORINE not in active_entity_keys(CHLORINE_OPTIONS)


async def test_combined_chlorine_needs_one_test_session(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    tracker = salt_entry.runtime_data.tracker
    now = dt_util.utcnow()

    # Nothing measured yet
    assert tracker.combined_chlorine is None

    # Same session: total minus free
    tracker.values[KEY_FREE_CHLORINE] = 1.5
    tracker.values[KEY_TOTAL_CHLORINE] = 2.2
    tracker.values_at[KEY_FREE_CHLORINE] = now.isoformat()
    tracker.values_at[KEY_TOTAL_CHLORINE] = now.isoformat()
    assert tracker.combined_chlorine == 0.7

    # A total below free is strip noise, not negative chloramine
    tracker.values[KEY_TOTAL_CHLORINE] = 1.0
    assert tracker.combined_chlorine == 0.0

    # A week between the two readings makes the subtraction meaningless
    tracker.values_at[KEY_FREE_CHLORINE] = (now - timedelta(days=7)).isoformat()
    assert tracker.combined_chlorine is None


async def test_cyanuric_band_depends_on_pool_type(
    hass, salt_entry, chlorine_entry, hass_client_no_auth
):
    await setup_entry(hass, salt_entry)
    await setup_entry(hass, chlorine_entry)
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    ranges = config["ranges"]
    assert ranges[KEY_CYANURIC_ACID] == {"min": 60.0, "max": 80.0}
    assert ranges[KEY_TOTAL_ALKALINITY] == {"min": 80.0, "max": 120.0}
    assert ranges[KEY_CALCIUM_HARDNESS] == {"min": 200.0, "max": 400.0}
    # Chloramine is reported, never judged: there is no band to sit in
    assert KEY_COMBINED_CHLORINE not in ranges

    chlorine_url = URL_PAGE.format(token=chlorine_entry.data["token"])
    config = extract_config(await (await client.get(chlorine_url)).text())
    assert config["ranges"][KEY_CYANURIC_ACID] == {"min": 30.0, "max": 50.0}


async def test_chemistry_reaches_report_task_list_and_history(
    hass, salt_entry, hass_client_no_auth
):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(
        LOG_URL,
        json={
            "person": "Lucas",
            "categories": ["water_test"],
            "readings": {
                "free_chlorine": 1.5,
                "total_chlorine": 2.5,
                "cyanuric_acid": 70,
                "calcium_hardness": 300,
                "total_alkalinity": 90,
            },
        },
    )
    assert response.status == 200
    await hass.async_block_till_done()

    state = await (await client.get(STATE_URL)).json()
    report = state["report"]
    assert report["values"][KEY_CYANURIC_ACID] == 70
    # Total and free came from the same record, so the derived figure exists
    assert report["combined_chlorine"] == 1.0

    tasks = {task["key"]: task for task in report["tasks"]}
    assert tasks["chemistry_test"]["interval_days"] == 30
    assert tasks["chemistry_test"]["last"] is not None
    assert tasks["chemistry_test"]["due"] is False

    response = await client.get(f"/api/pool_maintenance_tracker/{TEST_TOKEN}/history?days=7")
    data = await response.json()
    assert data["readings"][KEY_CYANURIC_ACID]["manual"][0]["v"] == 70
    assert data["readings"][KEY_CYANURIC_ACID]["unit"] == "ppm"
    assert data["readings"][KEY_TOTAL_ALKALINITY]["manual"][0]["v"] == 90


async def test_combined_chlorine_sensor_entity(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    registry = er.async_get(hass)
    entity_id = registry.async_get_entity_id(
        "sensor", DOMAIN, f"{salt_entry.entry_id}_{KEY_COMBINED_CHLORINE}"
    )
    assert entity_id is not None
    assert hass.states.get(entity_id).state == "unknown"

    response = await client.post(
        LOG_URL,
        json={"readings": {"free_chlorine": 1.0, "total_chlorine": 2.0}},
    )
    assert response.status == 200
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "1.0"
