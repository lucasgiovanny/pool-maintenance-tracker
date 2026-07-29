"""Maintenance mode: the flag, its switch, and the toggles that reach it."""

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    CONF_MAINTENANCE_MODE,
    CONF_SALT_TARGET_MAX,
    CONF_SALT_TARGET_MIN,
    DOMAIN,
    URL_MODE,
    URL_STATE,
)

from .conftest import TEST_TOKEN, setup_entry
from .test_http_page import PAGE_URL, extract_config

MODE_URL = URL_MODE.format(token=TEST_TOKEN)


def switch_id(hass, entry) -> str | None:
    registry = er.async_get(hass)
    return registry.async_get_entity_id("switch", DOMAIN, f"{entry.entry_id}_maintenance_mode")


async def setup_with_mode(hass, entry, enabled: bool = True) -> None:
    """Set the entry up with the maintenance mode feature on or off."""
    entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        entry, options={**entry.options, CONF_MAINTENANCE_MODE: enabled}
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_switch_exists_by_default(hass, salt_entry):
    """Nothing configured: the flag is there, off, ready for automations."""
    await setup_entry(hass, salt_entry)
    entity_id = switch_id(hass, salt_entry)
    assert entity_id
    assert hass.states.get(entity_id).state == "off"


async def test_no_switch_when_switched_off(hass, salt_entry):
    await setup_with_mode(hass, salt_entry, enabled=False)
    assert switch_id(hass, salt_entry) is None


async def test_switch_attributes(hass, salt_entry):
    await setup_with_mode(hass, salt_entry)
    entity_id = switch_id(hass, salt_entry)
    assert entity_id
    state = hass.states.get(entity_id)
    assert state.state == "off"
    assert state.attributes["since"] is None
    assert state.attributes["set_by"] is None


async def test_switch_writes_through_the_tracker(hass, salt_entry):
    await setup_with_mode(hass, salt_entry)
    entity_id = switch_id(hass, salt_entry)

    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )
    tracker = salt_entry.runtime_data.tracker
    assert tracker.maintenance_mode is True
    state = hass.states.get(entity_id)
    assert state.state == "on"
    assert state.attributes["since"]
    # flipped inside Home Assistant, where the logbook already says who
    assert state.attributes["set_by"] is None

    await hass.services.async_call(
        "switch",
        "turn_off",
        {"entity_id": entity_id},
        blocking=True,
    )
    assert tracker.maintenance_mode is False
    assert hass.states.get(entity_id).state == "off"


async def test_flag_survives_a_reload(hass, salt_entry):
    await setup_with_mode(hass, salt_entry)
    entity_id = switch_id(hass, salt_entry)
    await hass.services.async_call(
        "switch",
        "turn_on",
        {"entity_id": entity_id},
        blocking=True,
    )

    assert await hass.config_entries.async_reload(salt_entry.entry_id)
    await hass.async_block_till_done()

    # a technician who raised it and went home keeps it raised
    assert salt_entry.runtime_data.tracker.maintenance_mode is True
    assert hass.states.get(entity_id).state == "on"


async def test_page_toggles_the_mode(hass, salt_entry, hass_client_no_auth):
    await setup_with_mode(hass, salt_entry)
    client = await hass_client_no_auth()
    entity_id = switch_id(hass, salt_entry)

    response = await client.post(MODE_URL, json={"on": True, "person": "Técnico"})
    assert response.status == 200
    data = await response.json()
    assert data["ok"] is True
    assert data["on"] is True
    assert data["by"] == "Técnico"
    assert data["since"]
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "on"
    assert hass.states.get(entity_id).attributes["set_by"] == "Técnico"

    response = await client.post(MODE_URL, json={"on": False, "person": "Técnico"})
    assert response.status == 200
    assert (await response.json())["on"] is False
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == "off"


async def test_page_mode_rejects_bad_payloads(hass, salt_entry, hass_client_no_auth):
    await setup_with_mode(hass, salt_entry)
    client = await hass_client_no_auth()

    for payload in ({}, {"on": "yes"}, {"on": 1}, []):
        response = await client.post(MODE_URL, json=payload)
        assert response.status == 400
    assert salt_entry.runtime_data.tracker.maintenance_mode is False

    response = await client.post(URL_MODE.format(token="wrong"), json={"on": True})
    assert response.status == 404


async def test_page_mode_404_when_disabled(hass, salt_entry, hass_client_no_auth):
    await setup_with_mode(hass, salt_entry, enabled=False)
    client = await hass_client_no_auth()
    response = await client.post(MODE_URL, json={"on": True})
    assert response.status == 404
    assert salt_entry.runtime_data.tracker.maintenance_mode is False


async def test_page_and_state_expose_the_mode(hass, salt_entry, hass_client_no_auth):
    await setup_with_mode(hass, salt_entry)
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["mode_endpoint"] == MODE_URL
    assert config["maintenance_mode"] == {
        "enabled": True,
        "on": False,
        "since": None,
        "by": None,
    }
    # the card and the kiosk read it off the report
    assert config["report"]["maintenance_mode"]["enabled"] is True

    await client.post(MODE_URL, json={"on": True, "person": "Maria"})
    await hass.async_block_till_done()

    data = await (await client.get(URL_STATE.format(token=TEST_TOKEN))).json()
    assert data["maintenance_mode"]["on"] is True
    assert data["maintenance_mode"]["by"] == "Maria"
    assert data["report"]["maintenance_mode"]["on"] is True


async def test_kiosk_states_the_mode(hass, salt_entry, hass_client_no_auth):
    """The wall screen answers "is anybody working on the pool" either way."""
    from custom_components.pool_maintenance_tracker.const import URL_KIOSK

    from .test_kiosk import extract_config as extract_kiosk_config

    await setup_with_mode(hass, salt_entry)
    client = await hass_client_no_auth()
    kiosk_url = URL_KIOSK.format(token=TEST_TOKEN)

    config = extract_kiosk_config(await (await client.get(kiosk_url)).text())
    assert config["report"]["maintenance_mode"] == {
        "enabled": True,
        "on": False,
        "since": None,
        "by": None,
    }
    assert config["strings"]["maintenance"]["title"]

    await client.post(MODE_URL, json={"on": True, "person": "Técnico"})
    await hass.async_block_till_done()

    config = extract_kiosk_config(await (await client.get(kiosk_url)).text())
    assert config["report"]["maintenance_mode"]["on"] is True
    assert config["report"]["maintenance_mode"]["by"] == "Técnico"


async def test_page_reports_the_feature_off(hass, salt_entry, hass_client_no_auth):
    await setup_with_mode(hass, salt_entry, enabled=False)
    client = await hass_client_no_auth()
    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["maintenance_mode"]["enabled"] is False


async def test_options_flow_creates_and_removes_the_switch(hass, salt_entry):
    await setup_with_mode(hass, salt_entry, enabled=False)
    assert switch_id(hass, salt_entry) is None

    async def configure(enabled: bool) -> None:
        result = await hass.config_entries.options.async_init(salt_entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"next_step_id": "pool"}
        )
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {
                CONF_SALT_TARGET_MIN: 3,
                CONF_SALT_TARGET_MAX: 5,
                CONF_MAINTENANCE_MODE: enabled,
            },
        )
        assert result["type"] is FlowResultType.MENU
        await hass.async_block_till_done()

    await configure(True)
    assert salt_entry.options[CONF_MAINTENANCE_MODE] is True
    assert switch_id(hass, salt_entry)

    # switching the feature off prunes the entity again
    await configure(False)
    assert salt_entry.options[CONF_MAINTENANCE_MODE] is False
    assert switch_id(hass, salt_entry) is None
