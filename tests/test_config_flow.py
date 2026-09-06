"""Config flow tests."""

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.data_entry_flow import FlowResultType

from custom_components.pool_maintenance_tracker.const import (
    CONF_LANGUAGE,
    CONF_MODULES,
    CONF_POOL_TYPE,
    CONF_POOL_VOLUME,
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
        result["flow_id"], {CONF_LANGUAGE: "pt"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Piscina"
    entry = result["result"]
    assert entry.data[CONF_NAME] == "Piscina"
    assert len(entry.data[CONF_TOKEN]) > 30
    assert entry.options[CONF_POOL_TYPE] == POOL_TYPE_SALT
    assert entry.options[CONF_LANGUAGE] == "pt"
    assert entry.options[CONF_MODULES] == [
        "salt_chlorinator",
        "acid_tank",
        "filter",
        "ph_probe",
    ]

    await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()


async def test_settings_step_only_asks_for_the_language(hass):
    """Nothing periodic is configured any more — the page language is all."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_NAME: "Small pool", CONF_POOL_TYPE: POOL_TYPE_CHLORINE}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODULES: ["filter", "cleaning"]}
    )
    assert {str(key) for key in result["data_schema"].schema} == {CONF_LANGUAGE}

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LANGUAGE: "en"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY

    await hass.config_entries.async_unload(result["result"].entry_id)
    await hass.async_block_till_done()


async def test_volume_is_optional_at_creation(hass):
    """Skipping the volume only costs the salt-dose hint."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {CONF_NAME: "Piscina", CONF_POOL_TYPE: POOL_TYPE_SALT, CONF_POOL_VOLUME: 45},
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_MODULES: ["salt_chlorinator"]}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_LANGUAGE: "pt"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_POOL_VOLUME] == 45.0
