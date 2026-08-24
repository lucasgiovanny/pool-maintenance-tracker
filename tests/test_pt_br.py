"""Brazilian Portuguese, end to end.

Home Assistant treats pt-BR as its own language and never falls back to
pt for custom integrations — a pt-BR install got English everywhere.
These tests hold the fix: a pt-BR bundle exists on both sides, and every
place that resolves a language prefers the exact regional code, then its
base, then English.
"""

import json
import re

from homeassistant.data_entry_flow import FlowResultType

from custom_components.pool_maintenance_tracker.const import (
    CONF_LANGUAGE,
    DOMAIN,
    URL_PAGE,
)

from .conftest import TEST_TOKEN, setup_entry


def extract_config(html: str) -> dict:
    match = re.search(r"const CFG = (\{.*?\});\n", html, re.DOTALL)
    assert match, "injected config not found"
    return json.loads(match.group(1).replace("<\\/", "</"))


async def test_native_translations_exist_for_pt_br(hass):
    """The file HA actually loads for a pt-BR install."""
    data = json.load(open("custom_components/pool_maintenance_tracker/translations/pt-BR.json"))
    assert data["entity"]["select"]["acid_tank_level"]["state"]["none"] == "Sem tanque"
    assert data["entity"]["sensor"]["last_record"]["name"] == "Último registro"
    assert data["config"]["step"]["user"]["title"] == "Adicionar uma piscina"
    # Brazilian voice, not just a copy of pt
    assert "Você pode" in data["config"]["step"]["user"]["data_description"]["pool_type"]


async def test_card_language_pt_br_gets_its_own_bundle(hass, salt_entry, hass_ws_client):
    await setup_entry(hass, salt_entry)
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/status",
            "entry_id": salt_entry.entry_id,
            "language": "pt-BR",
        }
    )
    result = await client.receive_json()
    assert result["success"]
    assert result["result"]["language"] == "pt-br"
    assert result["result"]["strings"]["save"] == "Salvar registro"


async def test_unknown_region_falls_back_to_its_base(hass, salt_entry, hass_ws_client):
    """en-GB is not a bundle we ship; en is."""
    await setup_entry(hass, salt_entry)
    client = await hass_ws_client(hass)
    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/status",
            "entry_id": salt_entry.entry_id,
            "language": "en-GB",
        }
    )
    result = await client.receive_json()
    assert result["result"]["language"] == "en"


async def test_page_can_speak_pt_br(hass, salt_entry, hass_client_no_auth):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, CONF_LANGUAGE: "pt-br"}
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(URL_PAGE.format(token=TEST_TOKEN))).text())
    assert config["language"] == "pt-br"
    assert config["strings"]["save"] == "Salvar registro"
    assert config["strings"]["report"]["export_csv"] == "Baixar o registro (CSV)"


async def test_config_flow_defaults_to_the_exact_regional_code(hass):
    """A pt-BR install gets a pt-BR page by default, not pt."""
    hass.config.language = "pt-BR"
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": "user"})
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"name": "Piscina BR", "pool_type": "salt"}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"modules": ["filter"]}
    )
    assert result["type"] is FlowResultType.FORM
    schema = result["data_schema"].schema
    language_key = next(key for key in schema if key.schema == CONF_LANGUAGE)
    assert language_key.default() == "pt-br"
