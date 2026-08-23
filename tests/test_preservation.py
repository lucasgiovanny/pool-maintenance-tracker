"""The v0.47 promises: the history survives, and the data can leave.

Statistics mirrors for the measurements, the CSV/service export, and the
logbook sentence — everything that turns "the integration keeps a log"
into "Home Assistant keeps the pool's history".
"""

from homeassistant.core import Event
from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    DOMAIN,
    EVENT_RECORD,
    URL_EXPORT,
    URL_LOG,
)
from custom_components.pool_maintenance_tracker.logbook import async_describe_events

from .conftest import TEST_TOKEN, setup_entry

LOG_URL = URL_LOG.format(token=TEST_TOKEN)
EXPORT_URL = URL_EXPORT.format(token=TEST_TOKEN)


async def test_measurements_mirror_into_statistics_sensors(hass, salt_entry):
    """Each enabled reading gets a sensor HA compiles statistics for."""
    await setup_entry(hass, salt_entry)

    state = hass.states.get("sensor.piscina_ph")
    assert state is not None
    assert state.attributes["state_class"] == "measurement"

    ph_number = hass.states.get("number.piscina_ph_manual_reading")
    assert ph_number is not None

    await hass.services.async_call(
        "number",
        "set_value",
        {"entity_id": "number.piscina_ph_manual_reading", "value": 7.3},
        blocking=True,
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.piscina_ph").state == "7.3"

    # Temperature mirror carries the device class that unlocks conversion
    temp = hass.states.get("sensor.piscina_water_temperature")
    assert temp is not None
    assert temp.attributes.get("device_class") == "temperature"


async def test_mirrors_follow_their_module(hass, chlorine_entry):
    """No salt module, no salt mirror — same gating as the number."""
    await setup_entry(hass, chlorine_entry)
    registry = er.async_get(hass)
    assert (
        registry.async_get_entity_id(
            "sensor", DOMAIN, f"{chlorine_entry.entry_id}_salt_level_measurement"
        )
        is None
    )
    assert registry.async_get_entity_id(
        "sensor", DOMAIN, f"{chlorine_entry.entry_id}_ph_measurement"
    )


async def test_export_service_returns_the_log(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    await client.post(
        LOG_URL,
        json={
            "person": "Lucas",
            "categories": ["filter_wash"],
            "readings": {"ph": 7.4},
            "note": "Primeira lavagem",
        },
    )
    await hass.async_block_till_done()

    response = await hass.services.async_call(
        DOMAIN,
        "export_records",
        {"config_entry": salt_entry.entry_id},
        blocking=True,
        return_response=True,
    )
    assert response["pool"] == "Piscina"
    assert len(response["records"]) == 1
    assert response["records"][0]["person"] == "Lucas"
    assert response["records"][0]["data"]["ph"] == 7.4


async def test_export_csv_download(hass, salt_entry, hass_client_no_auth):
    """One row per record, columns for every value the pool ever used."""
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    await client.post(
        LOG_URL,
        json={"person": "Lucas", "categories": ["water_test"], "readings": {"ph": 7.2}},
    )
    await client.post(
        LOG_URL,
        json={"person": "Ana, a técnica", "salt": {"added_kg": 25}},
    )
    await hass.async_block_till_done()

    response = await client.get(EXPORT_URL)
    assert response.status == 200
    assert response.content_type == "text/csv"
    assert "attachment" in response.headers["Content-Disposition"]
    lines = (await response.text()).strip().split("\r\n")
    header = lines[0].split(",")
    assert header[:4] == ["id", "logged_at", "person", "categories"]
    assert "ph" in header and "salt_added" in header
    assert len(lines) == 3
    # A person with a comma in the name survives the format
    assert '"Ana, a técnica"' in lines[2]


async def test_export_needs_the_token(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.get(URL_EXPORT.format(token="wrong-token"))
    assert response.status == 404


async def test_logbook_speaks_the_pool_language(hass, salt_entry, hass_client_no_auth):
    """The describer turns the bus event into a sentence, in pt here."""
    await setup_entry(hass, salt_entry)  # page language pt; strings preloaded

    captured = {}

    def describer(domain, event_type, callback_):
        captured["domain"] = domain
        captured["event"] = event_type
        captured["callback"] = callback_

    async_describe_events(hass, describer)
    assert captured["domain"] == DOMAIN
    assert captured["event"] == EVENT_RECORD

    event = Event(
        EVENT_RECORD,
        {
            "entry_id": salt_entry.entry_id,
            "pool_name": "Piscina",
            "person": "Lucas",
            "categories": ["filter_wash"],
            "data": {},
        },
    )
    entry = captured["callback"](event)
    assert entry["name"] == "Piscina"
    assert entry["message"] == "Lucas · Filtro lavado"


async def test_logbook_names_readings_without_categories(hass, salt_entry):
    """A readings-only record is described by what was measured."""
    await setup_entry(hass, salt_entry)
    captured = {}
    async_describe_events(hass, lambda d, e, cb: captured.update(callback=cb))
    event = Event(
        EVENT_RECORD,
        {
            "entry_id": salt_entry.entry_id,
            "pool_name": "Piscina",
            "person": "Lucas",
            "categories": [],
            "data": {"ph": 7.2},
        },
    )
    assert captured["callback"](event)["message"] == "Lucas · pH"
