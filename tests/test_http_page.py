"""Tests for the public page endpoint."""

import json
import re

from custom_components.pool_maintenance_tracker.const import URL_PAGE

from .conftest import TEST_TOKEN, setup_entry

PAGE_URL = URL_PAGE.format(token=TEST_TOKEN)


def extract_config(html: str) -> dict:
    match = re.search(r"const CFG = (\{.*?\});\n", html, re.DOTALL)
    assert match, "injected config not found"
    return json.loads(match.group(1).replace("<\\/", "</"))


async def test_page_serves_injected_config(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.get(PAGE_URL)
    assert response.status == 200
    assert response.headers["Content-Type"].startswith("text/html")
    assert response.headers["Cache-Control"] == "no-store"
    assert "Content-Security-Policy" in response.headers
    assert "X-Robots-Tag" in response.headers

    html = await response.text()
    assert "__POOL_CONFIG__" not in html

    config = extract_config(html)
    assert config["pool_name"] == "Piscina"
    assert config["language"] == "pt"
    assert config["endpoint"].endswith("/log")
    assert TEST_TOKEN in config["endpoint"]
    assert config["tiles"][0] == "water_test"
    assert "chlorinator" in config["tiles"]
    assert config["strings"]["title"] == "Registo de manutenção da piscina"
    assert "salt_level" in config["limits"]
    # technician chip is always the last person
    assert config["people"][-1] == "Técnico"


async def test_page_for_chlorine_pool_hides_salt_modules(hass, chlorine_entry, hass_client_no_auth):
    await setup_entry(hass, chlorine_entry)
    client = await hass_client_no_auth()
    token = chlorine_entry.data["token"]

    response = await client.get(URL_PAGE.format(token=token))
    assert response.status == 200
    config = extract_config(await response.text())
    assert "chlorinator" not in config["tiles"]
    assert "acid_refill" not in config["tiles"]
    assert "salt_level" not in config["limits"]
    assert config["language"] == "en"
    assert config["people"][-1] == "Technician"


async def test_page_lists_ha_users(hass, salt_entry, hass_client_no_auth):
    await hass.auth.async_create_user("Maria")
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.get(PAGE_URL)
    config = extract_config(await response.text())
    assert "Maria" in config["people"]


async def test_people_option_filters_users(hass, salt_entry, hass_client_no_auth):
    maria = await hass.auth.async_create_user("Maria")
    await hass.auth.async_create_user("João")
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, "people_users": [maria.id]}
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    response = await client.get(PAGE_URL)
    config = extract_config(await response.text())
    assert "Maria" in config["people"]
    assert "João" not in config["people"]
    assert config["people"][-1] == "Técnico"


async def test_page_has_date_picker(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    html = await (await client.get(PAGE_URL)).text()
    assert 'type="date"' in html
    config = extract_config(html)
    assert "other" not in config["tiles"]


async def test_page_unknown_token_404(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.get(URL_PAGE.format(token="nope"))
    assert response.status == 404
