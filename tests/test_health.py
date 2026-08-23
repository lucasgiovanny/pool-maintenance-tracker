"""Repair issues for configuration that points at nothing."""

from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from custom_components.pool_maintenance_tracker.const import DOMAIN

from .conftest import setup_entry


def _our_issues(hass) -> list[str]:
    registry = ir.async_get(hass)
    return [issue_id for domain, issue_id in registry.issues if domain == DOMAIN]


async def test_a_missing_entity_raises_an_issue(hass, salt_entry):
    """A configured id that answers to nothing is worth a repair card."""
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "pump_entity": "switch.gone_forever"},
    )
    await setup_entry(hass, salt_entry)

    issues = _our_issues(hass)
    assert len(issues) == 1
    assert issues[0] == f"missing_{salt_entry.entry_id}_pump_entity"
    issue = ir.async_get(hass).async_get_issue(DOMAIN, issues[0])
    assert issue.translation_placeholders["entity_id"] == "switch.gone_forever"
    assert issue.translation_placeholders["pool"] == "Piscina"


async def test_a_present_entity_raises_nothing(hass, salt_entry):
    """Present means a state or a registry entry — either satisfies."""
    hass.states.async_set("switch.pump", "on")
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry, options={**salt_entry.options, "pump_entity": "switch.pump"}
    )
    await setup_entry(hass, salt_entry)
    assert _our_issues(hass) == []


async def test_the_issue_clears_when_the_entity_appears(hass, salt_entry):
    """Registering the missing entity heals the issue without a restart."""
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "ph_source": "sensor.probe_ph"},
    )
    await setup_entry(hass, salt_entry)
    assert len(_our_issues(hass)) == 1

    registry = er.async_get(hass)
    registry.async_get_or_create("sensor", "probe", "ph", suggested_object_id="probe_ph")
    await hass.async_block_till_done()
    assert _our_issues(hass) == []


async def test_report_sensors_are_watched_too(hass, salt_entry):
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "report_sensors": ["sensor.vanished"]},
    )
    await setup_entry(hass, salt_entry)
    issues = _our_issues(hass)
    assert issues == [f"missing_{salt_entry.entry_id}_report_sensor.vanished"]


async def test_removal_takes_the_issues_along(hass, salt_entry):
    """Deleting the pool must not leave its warnings behind."""
    salt_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        salt_entry,
        options={**salt_entry.options, "pump_entity": "switch.gone_forever"},
    )
    await setup_entry(hass, salt_entry)
    assert len(_our_issues(hass)) == 1

    await hass.config_entries.async_remove(salt_entry.entry_id)
    await hass.async_block_till_done()
    assert _our_issues(hass) == []


async def test_subscription_pushes_on_change(hass, salt_entry, hass_ws_client):
    """The card's subscription gets the first payload and then the deltas."""
    await setup_entry(hass, salt_entry)
    client = await hass_ws_client(hass)

    await client.send_json(
        {"id": 5, "type": f"{DOMAIN}/subscribe", "entry_id": salt_entry.entry_id}
    )
    result = await client.receive_json()
    assert result["success"]
    first = await client.receive_json()
    assert first["type"] == "event"
    assert first["event"]["title"] == "Piscina"

    salt_entry.runtime_data.tracker.async_set_value("ph", 7.1)
    pushed = await client.receive_json()
    assert pushed["event"]["report"]["values"]["ph"] == 7.1
