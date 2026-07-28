"""Options flow tests."""

from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import entity_registry as er

from custom_components.pool_maintenance_tracker.const import (
    CONF_CELL_DAYS,
    CONF_FILTER_DAYS,
    CONF_MODULES,
    CONF_POOL_VOLUME,
    CONF_PROBE_DAYS,
    CONF_REMINDER_TIME,
    CONF_SALT_TARGET_MAX,
    CONF_SALT_TARGET_MIN,
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
    assert result["type"] is FlowResultType.MENU
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
    assert result["type"] is FlowResultType.MENU
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
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    assert salt_entry.options["people_users"] == [maria.id]


async def test_sensors_options_step(hass, salt_entry):
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sensors"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "ph_source": "sensor.probe_ph",
            "report_sensors": ["switch.heat_pump", "sensor.heat_pump_power"],
        },
    )
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    assert salt_entry.options["ph_source"] == "sensor.probe_ph"
    assert salt_entry.options["report_sensors"] == [
        "switch.heat_pump",
        "sensor.heat_pump_power",
    ]
    assert "salt_source" not in salt_entry.options

    # clearing the fields unlinks sensors and report entities
    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "sensors"}
    )
    result = await hass.config_entries.options.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    assert "ph_source" not in salt_entry.options
    assert "report_sensors" not in salt_entry.options


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
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    assert salt_entry.options[CONF_FILTER_DAYS] == 10
    assert salt_entry.options[CONF_REMINDER_TIME] == "08:30"


async def test_menu_returns_after_each_step(hass, salt_entry):
    """Two sections can be edited without reopening Configure."""
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    flow_id = result["flow_id"]

    result = await hass.config_entries.options.async_configure(
        flow_id, {"next_step_id": "reminders"}
    )
    result = await hass.config_entries.options.async_configure(
        flow_id,
        {
            CONF_FILTER_DAYS: 12,
            CONF_PROBE_DAYS: 20,
            CONF_CELL_DAYS: 30,
            CONF_REMINDER_TIME: "09:00",
        },
    )
    assert result["type"] is FlowResultType.MENU

    # straight into another section, same open dialog
    result = await hass.config_entries.options.async_configure(flow_id, {"next_step_id": "modules"})
    assert result["step_id"] == "modules"
    result = await hass.config_entries.options.async_configure(flow_id, {CONF_MODULES: ["filter"]})
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()

    assert salt_entry.options[CONF_FILTER_DAYS] == 12
    assert salt_entry.options[CONF_MODULES] == ["filter"]


async def test_pool_options_step(hass, salt_entry):
    """Volume and the salt band the readings are judged against."""
    await setup_entry(hass, salt_entry)

    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pool"}
    )
    assert result["step_id"] == "pool"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_POOL_VOLUME: 60, CONF_SALT_TARGET_MIN: 3, CONF_SALT_TARGET_MAX: 5},
    )
    assert result["type"] is FlowResultType.MENU
    await hass.async_block_till_done()
    assert salt_entry.options[CONF_POOL_VOLUME] == 60.0
    assert salt_entry.options[CONF_SALT_TARGET_MIN] == 3.0
    assert salt_entry.options[CONF_SALT_TARGET_MAX] == 5.0

    # clearing the volume drops it — the page then hides the dose hint
    result = await hass.config_entries.options.async_init(salt_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "pool"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SALT_TARGET_MIN: 3, CONF_SALT_TARGET_MAX: 5}
    )
    await hass.async_block_till_done()
    assert CONF_POOL_VOLUME not in salt_entry.options
