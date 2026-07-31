"""The maintenance window: doing what was asked, and undoing it after."""

from datetime import timedelta

import pytest
from homeassistant.const import CONF_NAME
from homeassistant.exceptions import ServiceValidationError
from homeassistant.util import dt as dt_util
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    async_mock_service,
)

from custom_components.pool_maintenance_tracker.const import (
    CONF_MAINTENANCE_MODE,
    CONF_TOKEN,
    DOMAIN,
    URL_MODE,
)

from .conftest import SALT_OPTIONS, TEST_TOKEN, setup_entry
from .test_http_page import PAGE_URL, extract_config
from .test_maintenance_mode import MODE_URL, switch_id

EQUIPMENT_OPTIONS = {
    **SALT_OPTIONS,
    CONF_MAINTENANCE_MODE: True,
    # An input_boolean on purpose: mocking a service replaces it for the whole
    # domain, and our own maintenance switch lives in `switch`.
    "pool_system_entity": "input_boolean.pool_system",
    "heat_pump_entity": "climate.heat_pump",
    "cover_entity": "cover.pool_cover",
    # A role that only observes: it can never be asked to do anything.
    "pump_entity": "binary_sensor.pump_running",
    # Configuration, not an appliance.
    "filtration_schedule_entity": "schedule.filtration",
}


@pytest.fixture
def pool(hass) -> MockConfigEntry:
    """A pool with equipment roles and the maintenance flag switched on."""
    hass.states.async_set("input_boolean.pool_system", "on", {"friendly_name": "Pool System"})
    hass.states.async_set("climate.heat_pump", "off", {"friendly_name": "Heat pump"})
    hass.states.async_set("cover.pool_cover", "closed", {"friendly_name": "Cover"})
    hass.states.async_set("binary_sensor.pump_running", "on", {"friendly_name": "Pump"})
    hass.states.async_set("schedule.filtration", "on", {"friendly_name": "Filtration"})
    return MockConfigEntry(
        domain=DOMAIN,
        title="Piscina",
        data={CONF_NAME: "Piscina", CONF_TOKEN: TEST_TOKEN},
        options=dict(EQUIPMENT_OPTIONS),
    )


async def test_the_sheet_only_offers_what_it_can_command(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    offered = {item["role"]: item for item in config["maintenance_equipment"]}

    assert offered["pool_system"]["state"] == "on"
    assert offered["pool_system"]["values"] == ["on", "off"]
    assert offered["heat_pump"]["name"] == "Heat pump"
    # a cover opens and closes; it does not turn on
    assert offered["cover"]["values"] == ["open", "closed"]
    # observation, not control
    assert "pump" not in offered
    # a schedule helper has no on/off service
    assert "filtration_schedule" not in offered


async def test_starting_a_visit_moves_the_equipment(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()
    turn_off = async_mock_service(hass, "input_boolean", "turn_off")
    turn_on = async_mock_service(hass, "climate", "turn_on")
    open_cover = async_mock_service(hass, "cover", "open_cover")

    response = await client.post(
        MODE_URL,
        json={
            "on": True,
            "person": "Técnico",
            "minutes": 60,
            "equipment": {"pool_system": "off", "heat_pump": "on", "cover": "open"},
        },
    )
    assert response.status == 200
    data = await response.json()
    assert data["applied"] == {"pool_system": "off", "heat_pump": "on", "cover": "open"}
    assert data["failed"] == {}
    assert data["until"]

    assert turn_off[0].data["entity_id"] == "input_boolean.pool_system"
    assert turn_on[0].data["entity_id"] == "climate.heat_pump"
    assert open_cover[0].data["entity_id"] == "cover.pool_cover"

    tracker = pool.runtime_data.tracker
    assert tracker.maintenance_mode is True
    # what it was, so the window knows where to put it back
    assert tracker.maintenance_mode_restore == {
        "pool_system": "on",
        "heat_pump": "off",
        "cover": "closed",
    }
    assert hass.states.get(switch_id(hass, pool)).attributes["until"] == data["until"]


async def test_roles_left_alone_are_never_touched(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()
    turn_off = async_mock_service(hass, "input_boolean", "turn_off")
    climate_off = async_mock_service(hass, "climate", "turn_off")

    await client.post(MODE_URL, json={"on": True, "equipment": {"pool_system": "off"}})
    await hass.async_block_till_done()

    assert len(turn_off) == 1
    assert climate_off == []
    assert "heat_pump" not in pool.runtime_data.tracker.maintenance_mode_restore


async def test_unknown_roles_and_words_are_reported_not_obeyed(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()
    async_mock_service(hass, "input_boolean", "turn_off")

    response = await client.post(
        MODE_URL,
        json={
            "on": True,
            "equipment": {
                "pool_system": "off",
                "heat_pump": "open",  # not a cover
                "pump": "off",  # a binary_sensor role
                "spaceship": "on",  # not a role at all
            },
        },
    )
    assert response.status == 200
    data = await response.json()
    assert data["applied"] == {"pool_system": "off"}
    assert sorted(data["ignored"]) == [
        "equipment.heat_pump",
        "equipment.pump",
        "equipment.spaceship",
    ]


async def test_a_role_that_cannot_be_reached_is_reported(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()
    hass.states.async_set("input_boolean.pool_system", "unavailable")

    response = await client.post(MODE_URL, json={"on": True, "equipment": {"pool_system": "off"}})
    assert response.status == 200
    data = await response.json()
    assert data["failed"] == {"pool_system": "unavailable"}
    assert data["applied"] == {}
    # nothing moved, so there is nothing to put back
    assert pool.runtime_data.tracker.maintenance_mode_restore == {}


async def test_minutes_outside_the_range_are_refused(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()

    for minutes in (1, 4000, "an hour", True):
        response = await client.post(MODE_URL, json={"on": True, "minutes": minutes})
        assert response.status == 400
    assert pool.runtime_data.tracker.maintenance_mode is False

    # absent, null and zero all mean "no limit"
    for minutes in (None, 0):
        response = await client.post(MODE_URL, json={"on": True, "minutes": minutes})
        assert response.status == 200
        assert (await response.json())["until"] is None


async def test_re_arming_keeps_since_and_the_original_snapshot(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()
    async_mock_service(hass, "input_boolean", "turn_off")

    first = await (
        await client.post(
            MODE_URL, json={"on": True, "minutes": 30, "equipment": {"pool_system": "off"}}
        )
    ).json()
    # the technician now thinks it will take longer, and asks again
    hass.states.async_set("input_boolean.pool_system", "off")
    second = await (
        await client.post(
            MODE_URL, json={"on": True, "minutes": 120, "equipment": {"pool_system": "off"}}
        )
    ).json()

    assert second["since"] == first["since"]  # the visit did not restart
    assert second["until"] != first["until"]
    # still "on": the state before the visit, not the state we left behind
    assert pool.runtime_data.tracker.maintenance_mode_restore == {"pool_system": "on"}


async def test_ending_the_visit_puts_the_equipment_back(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()
    async_mock_service(hass, "input_boolean", "turn_off")
    turn_on = async_mock_service(hass, "input_boolean", "turn_on")

    await client.post(MODE_URL, json={"on": True, "equipment": {"pool_system": "off"}})
    hass.states.async_set("input_boolean.pool_system", "off")

    response = await client.post(MODE_URL, json={"on": False})
    assert response.status == 200
    assert (await response.json())["on"] is False
    await hass.async_block_till_done()

    # the session restores on the flag dropping, wherever it was dropped —
    # and the photograph is taken away with it, so it happens exactly once
    assert turn_on[0].data["entity_id"] == "input_boolean.pool_system"
    assert len(turn_on) == 1
    assert pool.runtime_data.tracker.maintenance_mode_restore == {}


async def test_equipment_somebody_else_moved_is_left_alone(hass, pool, hass_client_no_auth):
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()
    async_mock_service(hass, "input_boolean", "turn_off")
    turn_on = async_mock_service(hass, "input_boolean", "turn_on")

    await client.post(MODE_URL, json={"on": True, "equipment": {"pool_system": "off"}})
    # somebody turned it back on during the visit — theirs is the newer word
    hass.states.async_set("input_boolean.pool_system", "on")

    await client.post(MODE_URL, json={"on": False})
    await hass.async_block_till_done()
    assert turn_on == []


async def test_the_window_closes_itself(hass, pool):
    await setup_entry(hass, pool)
    async_mock_service(hass, "input_boolean", "turn_off")
    turn_on = async_mock_service(hass, "input_boolean", "turn_on")
    tracker = pool.runtime_data.tracker

    from custom_components.pool_maintenance_tracker import maintenance

    until = (dt_util.utcnow() + timedelta(minutes=30)).isoformat()
    tracker.async_set_maintenance_mode(True, until=until, plan={"pool_system": "off"})
    await maintenance.async_apply(hass, pool, {"pool_system": "off"})
    hass.states.async_set("input_boolean.pool_system", "off")
    await hass.async_block_till_done()

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(minutes=31))
    await hass.async_block_till_done()

    assert tracker.maintenance_mode is False
    assert tracker.maintenance_mode_until is None
    # the flag dropping is what puts the equipment back
    assert turn_on[0].data["entity_id"] == "input_boolean.pool_system"


async def test_a_window_that_ran_out_while_off_closes_at_startup(hass, pool, hass_storage):
    """A restart must not resurrect a visit that ended hours ago."""
    hass_storage[f"{DOMAIN}.{pool.entry_id}"] = {
        "version": 1,
        "key": f"{DOMAIN}.{pool.entry_id}",
        "data": {
            "maintenance_mode": True,
            "maintenance_mode_at": (dt_util.utcnow() - timedelta(hours=3)).isoformat(),
            "maintenance_mode_until": (dt_util.utcnow() - timedelta(hours=2)).isoformat(),
            "maintenance_mode_plan": {"pool_system": "off"},
            "maintenance_mode_restore": {"pool_system": "on"},
        },
    }
    hass.states.async_set("input_boolean.pool_system", "off")
    turn_on = async_mock_service(hass, "input_boolean", "turn_on")

    await setup_entry(hass, pool)
    await hass.async_block_till_done()

    assert pool.runtime_data.tracker.maintenance_mode is False
    assert turn_on[0].data["entity_id"] == "input_boolean.pool_system"


async def test_the_switch_ends_the_visit_too(hass, pool):
    await setup_entry(hass, pool)
    async_mock_service(hass, "input_boolean", "turn_off")
    turn_on = async_mock_service(hass, "input_boolean", "turn_on")

    await hass.services.async_call(
        DOMAIN,
        "start_maintenance",
        {
            "config_entry": pool.entry_id,
            "minutes": 60,
            "equipment": {"pool_system": "off"},
        },
        blocking=True,
    )
    assert pool.runtime_data.tracker.maintenance_mode is True
    assert pool.runtime_data.tracker.maintenance_mode_until
    hass.states.async_set("input_boolean.pool_system", "off")

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": switch_id(hass, pool)},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert pool.runtime_data.tracker.maintenance_mode is False
    assert turn_on[0].data["entity_id"] == "input_boolean.pool_system"


async def test_the_action_refuses_a_bad_window(hass, pool):
    await setup_entry(hass, pool)

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "start_maintenance",
            {"config_entry": pool.entry_id, "minutes": 5000},
            blocking=True,
        )
    assert pool.runtime_data.tracker.maintenance_mode is False


async def test_the_action_refuses_a_pool_with_the_feature_off(hass, salt_entry):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, CONF_MAINTENANCE_MODE: False}
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "start_maintenance",
            {"config_entry": salt_entry.entry_id},
            blocking=True,
        )


async def test_the_page_can_poll_the_flag_on_its_own(hass, pool, hass_client_no_auth):
    """The status tab is optional; noticing a window close is not."""
    await setup_entry(hass, pool)
    client = await hass_client_no_auth()

    response = await client.get(MODE_URL)
    assert response.status == 200
    assert (await response.json())["on"] is False

    async_mock_service(hass, "input_boolean", "turn_off")
    await client.post(MODE_URL, json={"on": True, "minutes": 60, "person": "Maria"})

    data = await (await client.get(MODE_URL)).json()
    assert data["on"] is True
    assert data["by"] == "Maria"
    assert data["until"]

    assert (await client.get(URL_MODE.format(token="wrong"))).status == 404
