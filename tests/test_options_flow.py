"""Options flow tests."""

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    CONF_CELL_DAYS,
    CONF_FILTER_DAYS,
    CONF_MODULES,
    CONF_PROBE_DAYS,
    CONF_REMINDER_TIME,
    CONF_TOKEN,
    URL_PAGE,
)

from .conftest import TEST_TOKEN, setup_entry


async def test_disable_module_removes_entities(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    registry = er.async_get(hass)
    assert registry.async_get_entity_id(
        "select", "pool_maintenance_tracker", f"{salt_entry.entry_id}_chlorinator_mode"
    )

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "modules"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_MODULES: ["filter", "cleaning"]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    assert salt_entry.options[CONF_MODULES] == ["filter", "cleaning"]
    assert (
        registry.async_get_entity_id(
            "select",
            "pool_maintenance_tracker",
            f"{salt_entry.entry_id}_chlorinator_mode",
        )
        is None
    )
    # still present
    assert registry.async_get_entity_id(
        "number", "pool_maintenance_tracker", f"{salt_entry.entry_id}_ph"
    )


async def test_regenerate_token(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "security"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"regenerate_token": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()

    new_token = salt_entry.data[CONF_TOKEN]
    assert new_token != TEST_TOKEN

    response = await client.get(URL_PAGE.format(token=TEST_TOKEN))
    assert response.status == 404
    response = await client.get(URL_PAGE.format(token=new_token))
    assert response.status == 200


async def test_people_options_step(hass, salt_entry):
    maria = await hass.auth.async_create_user("Maria")
    await hass.auth.async_create_user("João")
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "people"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"people_users": [maria.id]}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert salt_entry.options["people_users"] == [maria.id]


async def test_sensors_options_step(hass, salt_entry):
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sensors"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"ph_source": "sensor.probe_ph"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert salt_entry.options["ph_source"] == "sensor.probe_ph"
    assert "salt_source" not in salt_entry.options

    # clearing the field unlinks the sensor
    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sensors"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert "ph_source" not in salt_entry.options


async def test_reminder_options_update(hass, salt_entry):
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "reminders"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_FILTER_DAYS: 10,
            CONF_PROBE_DAYS: 20,
            CONF_CELL_DAYS: 30,
            CONF_REMINDER_TIME: "08:30",
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert salt_entry.options[CONF_FILTER_DAYS] == 10
    assert salt_entry.options[CONF_REMINDER_TIME] == "08:30"
