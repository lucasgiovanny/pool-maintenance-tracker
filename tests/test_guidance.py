"""Ideal bands, pool volume and the filtration suggestion.

These three feed every surface (page, kiosk, card) from the same payload,
so the tests here work on the page config and the /state endpoint.
"""

import json
import re

from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    CONF_CELL_OUTPUT,
    CONF_COVER_ENTITY,
    CONF_FILTRATION_SCHEDULE_ENTITY,
    CONF_POOL_VOLUME,
    CONF_PUMP_ENTITY,
    CONF_PUMP_FLOW,
    CONF_PUMP_TYPE,
    CONF_SALT_TARGET_MAX,
    CONF_SALT_TARGET_MIN,
    CONF_TEMPERATURE_SOURCE,
    CONF_UV_SOURCE,
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


async def test_sizing_reaches_every_surface(hass, salt_entry, hass_client_no_auth):
    """A big pool on a weak pump gets more hours, everywhere at once."""
    hass.states.async_set("sensor.probe_temperature", "28", {"unit_of_measurement": "°C"})
    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_POOL_VOLUME: 80,
            CONF_PUMP_FLOW: 8,
            CONF_PUMP_TYPE: "variable_speed",
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["basis"] == "turnover"
    assert hint["recommended_hours"] == 20.0  # the rule of thumb would say 14 h
    assert hint["turnovers"] == 2.0
    assert hint["low_speed_hours"] == 24.0

    state = await (await client.get(STATE_URL)).json()
    assert state["report"]["filtration"]["recommended_hours"] == 20.0


async def test_a_flow_rate_can_never_under_filter(hass, salt_entry, hass_client_no_auth):
    """The nameplate figure is unverifiable, so it only ever raises hours."""
    hass.states.async_set("sensor.probe_temperature", "25", {"unit_of_measurement": "°C"})
    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_POOL_VOLUME: 26,
            CONF_PUMP_FLOW: 10,
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["turnover_hours"] == 4.5
    assert hint["recommended_hours"] == 12.5  # the baseline wins
    assert hint["basis"] == "rule_of_thumb"


async def test_uv_reaches_the_advice(hass, salt_entry, hass_client_no_auth):
    """Read from a plain sensor or from a weather entity's attribute."""
    hass.states.async_set("sensor.probe_temperature", "30", {"unit_of_measurement": "°C"})
    hass.states.async_set("weather.home", "sunny", {"uv_index": 10})
    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_POOL_VOLUME: 60,
            CONF_PUMP_FLOW: 20,
            CONF_CELL_OUTPUT: 6,
            CONF_UV_SOURCE: "weather.home",
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["uv"] == 10.0
    assert hint["basis"] == "chlorination"
    assert hint["chlorine_hours"] == 26.0  # capped to 24 h once recommended


async def test_a_small_cell_takes_over_from_turnover(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set("sensor.probe_temperature", "30", {"unit_of_measurement": "°C"})
    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_POOL_VOLUME: 60,
            CONF_PUMP_FLOW: 20,
            CONF_CELL_OUTPUT: 6,
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["basis"] == "chlorination"
    assert hint["recommended_hours"] == 20.0


async def test_a_closed_cover_is_read_from_the_entity(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set("sensor.probe_temperature", "28", {"unit_of_measurement": "°C"})
    hass.states.async_set("cover.pool_cover", "closed", {"friendly_name": "Cobertura"})
    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_POOL_VOLUME: 48,
            CONF_PUMP_FLOW: 9,
            CONF_COVER_ENTITY: "cover.pool_cover",
        },
    )
    client = await hass_client_no_auth()

    covered = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert covered["covered"] is True

    hass.states.async_set("cover.pool_cover", "open")
    await hass.async_block_till_done()
    opened = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert opened["covered"] is False
    assert opened["recommended_hours"] > covered["recommended_hours"]


async def test_actual_hours_absent_without_a_recorder(hass, salt_entry, hass_client_no_auth):
    """The comparison degrades to nothing rather than to a wrong number."""
    hass.states.async_set("sensor.probe_temperature", "24", {"unit_of_measurement": "°C"})
    hass.states.async_set("switch.pump", "on", {"friendly_name": "Bomba"})
    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_PUMP_ENTITY: "switch.pump",
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["actual_hours"] is None


async def test_acid_tank_covers_empty_and_missing(hass, salt_entry, hass_client_no_auth):
    """A dry drum is an alert; no drum at all is a decision, not a fault."""
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    log_url = f"/api/pool_maintenance_tracker/{TEST_TOKEN}/log"

    response = await client.post(
        log_url,
        json={"person": "technician", "categories": ["acid_refill"], "acid": {"level": "empty"}},
    )
    assert response.status == 200
    await hass.async_block_till_done()
    assert salt_entry.runtime_data.tracker.values["acid_tank_level"] == "empty"
    assert hass.states.get("select.piscina_acid_tank_level").state == "empty"

    response = await client.post(
        log_url,
        json={"person": "technician", "categories": ["acid_refill"], "acid": {"level": "none"}},
    )
    assert response.status == 200
    await hass.async_block_till_done()
    assert salt_entry.runtime_data.tracker.values["acid_tank_level"] == "none"

    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["strings"]["acid_levels"]["none"]


async def test_the_freshest_reading_wins(hass, salt_entry, hass_client_no_auth):
    """A probe reading now beats last week's manual entry, and vice versa."""
    hass.states.async_set("sensor.probe_temperature", "27.4", {"unit_of_measurement": "°C"})
    await setup_with_options(
        hass, salt_entry, **{CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature"}
    )
    client = await hass_client_no_auth()

    # nothing logged yet: the probe is all there is
    current = extract_config(await (await client.get(PAGE_URL)).text())["report"]["current"]
    assert current["water_temperature"] == {
        "value": 27.4,
        "unit": "°C",
        "source": "probe",
        "at": current["water_temperature"]["at"],
        "other": None,
    }

    # a manual reading taken now is the newer of the two
    await client.post(
        f"/api/pool_maintenance_tracker/{TEST_TOKEN}/log",
        json={
            "person": "technician",
            "categories": ["water_test"],
            "readings": {"temperature": 25.0},
        },
    )
    await hass.async_block_till_done()
    current = extract_config(await (await client.get(PAGE_URL)).text())["report"]["current"]
    assert current["water_temperature"]["value"] == 25.0
    assert current["water_temperature"]["source"] == "manual"
    assert current["water_temperature"]["other"] == 27.4

    # ...until the probe speaks again
    hass.states.async_set("sensor.probe_temperature", "26.2", {"unit_of_measurement": "°C"})
    await hass.async_block_till_done()
    current = extract_config(await (await client.get(PAGE_URL)).text())["report"]["current"]
    assert current["water_temperature"]["value"] == 26.2
    assert current["water_temperature"]["source"] == "probe"
    assert current["water_temperature"]["other"] == 25.0


async def test_a_back_dated_reading_does_not_beat_the_probe(hass, salt_entry, hass_client_no_auth):
    """Logging yesterday's measurement should not override a live probe."""
    from datetime import timedelta

    from homeassistant.util import dt as dt_util

    hass.states.async_set("sensor.probe_temperature", "27.4", {"unit_of_measurement": "°C"})
    await setup_with_options(
        hass, salt_entry, **{CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature"}
    )
    client = await hass_client_no_auth()
    await client.post(
        f"/api/pool_maintenance_tracker/{TEST_TOKEN}/log",
        json={
            "person": "technician",
            "categories": ["water_test"],
            "readings": {"temperature": 21.0},
            "logged_at": (dt_util.utcnow() - timedelta(days=1)).isoformat(),
        },
    )
    await hass.async_block_till_done()

    current = extract_config(await (await client.get(PAGE_URL)).text())["report"]["current"]
    assert current["water_temperature"]["value"] == 27.4
    assert current["water_temperature"]["source"] == "probe"


async def test_the_filtration_advice_uses_the_same_temperature(
    hass, salt_entry, hass_client_no_auth
):
    """One resolved reading feeds the display and the maths alike."""
    hass.states.async_set("sensor.probe_temperature", "27.4", {"unit_of_measurement": "°C"})
    await setup_with_options(
        hass, salt_entry, **{CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature"}
    )
    client = await hass_client_no_auth()
    await client.post(
        f"/api/pool_maintenance_tracker/{TEST_TOKEN}/log",
        json={
            "person": "technician",
            "categories": ["water_test"],
            "readings": {"temperature": 20.0},
        },
    )
    await hass.async_block_till_done()

    report = extract_config(await (await client.get(PAGE_URL)).text())["report"]
    assert report["current"]["water_temperature"]["value"] == 20.0
    assert report["filtration"]["temperature"] == 20.0


async def test_a_short_schedule_raises_an_alert(
    hass, salt_entry, hass_client_no_auth, hass_storage
):
    """Scheduled well below the recommendation is worth saying out loud."""
    from homeassistant.helpers import entity_registry as er

    hass_storage["schedule"] = {
        "version": 1,
        "minor_version": 1,
        "key": "schedule",
        "data": {
            "items": [
                {
                    "id": "abc123",
                    "name": "Filtração",
                    **{
                        day: [{"from": "09:00:00", "to": "13:00:00"}]
                        for day in (
                            "monday",
                            "tuesday",
                            "wednesday",
                            "thursday",
                            "friday",
                            "saturday",
                            "sunday",
                        )
                    },
                }
            ]
        },
    }
    registry = er.async_get(hass)
    sched = registry.async_get_or_create(
        "schedule", "schedule", "abc123", suggested_object_id="filtracao"
    )
    hass.states.async_set(sched.entity_id, "on", {"friendly_name": "Filtração"})
    hass.states.async_set("sensor.probe_temperature", "26", {"unit_of_measurement": "°C"})

    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_FILTRATION_SCHEDULE_ENTITY: sched.entity_id,
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["scheduled_hours"] == 4.0
    assert hint["recommended_hours"] == 13.0
    assert hint["short_by"] == 9.0


async def test_a_schedule_within_tolerance_is_not_flagged(
    hass, salt_entry, hass_client_no_auth, hass_storage
):
    """Half an hour short is not news; it would just train people to ignore it."""
    from homeassistant.helpers import entity_registry as er

    hass_storage["schedule"] = {
        "version": 1,
        "minor_version": 1,
        "key": "schedule",
        "data": {
            "items": [
                {
                    "id": "abc123",
                    "name": "Filtração",
                    **{
                        day: [{"from": "08:00:00", "to": "20:30:00"}]
                        for day in (
                            "monday",
                            "tuesday",
                            "wednesday",
                            "thursday",
                            "friday",
                            "saturday",
                            "sunday",
                        )
                    },
                }
            ]
        },
    }
    registry = er.async_get(hass)
    sched = registry.async_get_or_create(
        "schedule", "schedule", "abc123", suggested_object_id="filtracao"
    )
    hass.states.async_set(sched.entity_id, "on", {"friendly_name": "Filtração"})
    hass.states.async_set("sensor.probe_temperature", "26", {"unit_of_measurement": "°C"})

    await setup_with_options(
        hass,
        salt_entry,
        **{
            CONF_TEMPERATURE_SOURCE: "sensor.probe_temperature",
            CONF_FILTRATION_SCHEDULE_ENTITY: sched.entity_id,
        },
    )
    client = await hass_client_no_auth()

    hint = extract_config(await (await client.get(PAGE_URL)).text())["report"]["filtration"]
    assert hint["scheduled_hours"] == 12.5
    assert hint["recommended_hours"] == 13.0
    assert hint["short_by"] is None


async def test_a_missing_acid_tank_is_its_own_alert(hass, salt_entry, hass_client_no_auth):
    """Nothing to refill, but the pH is no longer being dosed."""
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    await client.post(
        f"/api/pool_maintenance_tracker/{TEST_TOKEN}/log",
        json={"person": "technician", "categories": ["acid_refill"], "acid": {"level": "none"}},
    )
    await hass.async_block_till_done()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["report"]["values"]["acid_tank_level"] == "none"
    assert config["strings"]["report"]["alert_acid_missing"]
