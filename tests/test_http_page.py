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
    assert 'type="datetime-local"' in html
    config = extract_config(html)
    assert "other" not in config["tiles"]


async def test_linked_sensors_live_values(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set("sensor.probe_ph", "7.13")
    hass.states.async_set("sensor.probe_temp", "28.4", {"unit_of_measurement": "°C"})
    hass.states.async_set("sensor.probe_salt", "unavailable")
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={
            **salt_entry.options,
            "ph_source": "sensor.probe_ph",
            "temperature_source": "sensor.probe_temp",
            "salt_source": "sensor.probe_salt",
        },
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    response = await client.get(PAGE_URL)
    config = extract_config(await response.text())
    assert config["live"]["ph"] == {"value": 7.13, "unit": ""}
    assert config["live"]["temperature"] == {"value": 28.4, "unit": "°C"}
    # unavailable source is skipped entirely
    assert "salt" not in config["live"]
    assert config["linked_mode"] == "manual_only"


async def test_no_linked_sensors_means_empty_live(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["live"] == {}


async def test_report_tab_data(hass, salt_entry, hass_client_no_auth):
    from custom_components.pool_maintenance_tracker.const import URL_LOG

    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    response = await client.post(
        URL_LOG.format(token=TEST_TOKEN),
        json={
            "person": "Lucas",
            "categories": ["filter_wash"],
            "readings": {"ph": 7.3},
        },
    )
    assert response.status == 200
    await hass.async_block_till_done()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    report = config["report"]
    assert report["values"]["ph"] == 7.3
    task_keys = [task["key"] for task in report["tasks"]]
    assert "filter_wash" in task_keys
    filter_task = next(task for task in report["tasks"] if task["key"] == "filter_wash")
    assert filter_task["last"] is not None
    assert filter_task["interval_days"] == 30
    assert filter_task["due"] is False
    assert report["records"][0]["person"] == "Lucas"
    assert report["records"][0]["categories"] == ["filter_wash"]
    assert report["last_maintenance"] is not None


async def test_report_extra_sensors(hass, salt_entry, hass_client_no_auth):
    hass.states.async_set(
        "sensor.heat_pump_power",
        "1.25",
        {"friendly_name": "Heat pump power", "unit_of_measurement": "kW"},
    )
    hass.states.async_set("switch.heat_pump", "on", {"friendly_name": "Heat pump"})
    hass.states.async_set("sensor.broken", "unavailable")
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={
            **salt_entry.options,
            "report_sensors": [
                "sensor.heat_pump_power",
                "switch.heat_pump",
                "sensor.broken",
                "sensor.missing",
            ],
        },
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    extra = config["report"]["extra"]
    assert len(extra) == 2
    power = next(item for item in extra if item["entity_id"] == "sensor.heat_pump_power")
    assert power["name"] == "Heat pump power"
    assert power["state"] == "1.25"
    assert power["unit"] == "kW"
    pump = next(item for item in extra if item["entity_id"] == "switch.heat_pump")
    assert pump["state"] == "on"
    assert pump["domain"] == "switch"
    assert pump["last_changed"]


async def test_report_disabled_by_option(hass, salt_entry, hass_client_no_auth):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, "report_enabled": False}
    )
    assert await hass.config_entries.async_setup(salt_entry.entry_id)
    await hass.async_block_till_done()
    client = await hass_client_no_auth()

    config = extract_config(await (await client.get(PAGE_URL)).text())
    assert config["report"] is None


async def test_page_unknown_token_404(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    response = await client.get(URL_PAGE.format(token="nope"))
    assert response.status == 404
