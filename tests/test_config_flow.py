"""Config flow tests."""

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pool_maintenance_tracker.const import (
    CONF_CELL_DAYS,
    CONF_FILTER_DAYS,
    CONF_LANGUAGE,
    CONF_MODULES,
    CONF_NOTIFY_SERVICE,
    CONF_POOL_TYPE,
    CONF_PROBE_DAYS,
    CONF_TOKEN,
    DOMAIN,
    POOL_TYPE_CHLORINE,
    POOL_TYPE_SALT,
)


async def test_full_flow_salt_pool(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Piscina", CONF_POOL_TYPE: POOL_TYPE_SALT}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "modules"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_MODULES: ["salt_chlorinator", "acid_tank", "filter", "ph_probe"]},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "settings"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            CONF_LANGUAGE: "pt",
            CONF_NOTIFY_SERVICE: "notify.mobile_app_test",
            CONF_FILTER_DAYS: 15,
            CONF_PROBE_DAYS: 45,
            CONF_CELL_DAYS: 120,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Piscina"
    entry = result["result"]
    assert entry.data[CONF_NAME] == "Piscina"
    assert len(entry.data[CONF_TOKEN]) > 30
    assert entry.options[CONF_POOL_TYPE] == POOL_TYPE_SALT
    assert entry.options[CONF_MODULES] == [
        "salt_chlorinator",
        "acid_tank",
        "filter",
        "ph_probe",
    ]
    assert entry.options[CONF_FILTER_DAYS] == 15
    assert entry.options[CONF_PROBE_DAYS] == 45
    assert entry.options[CONF_CELL_DAYS] == 120

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_chlorine_pool_settings_has_no_cell_days(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Small pool", CONF_POOL_TYPE: POOL_TYPE_CHLORINE}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODULES: ["filter", "cleaning"]}
    )
    schema_keys = {str(key) for key in result["data_schema"].schema}
    assert CONF_FILTER_DAYS in schema_keys
    assert CONF_CELL_DAYS not in schema_keys
    assert CONF_PROBE_DAYS not in schema_keys

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LANGUAGE: "en", CONF_NOTIFY_SERVICE: "", CONF_FILTER_DAYS: 30},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].options[CONF_NOTIFY_SERVICE] == ""

    await hass.config_entries.async_unload(result["result"].entry_id)
    await hass.async_block_till_done()


async def test_invalid_notify_service_shows_error(hass):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "P", CONF_POOL_TYPE: POOL_TYPE_CHLORINE}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {CONF_MODULES: []})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_LANGUAGE: "en", CONF_NOTIFY_SERVICE: "not_a_service"},
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_NOTIFY_SERVICE: "invalid_notify_service"}
