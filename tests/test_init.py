"""Setup/unload lifecycle tests."""

from homeassistant.config_entries import ConfigEntryState

from custom_components.pool_maintenance_tracker.const import (
    CONF_TOKEN,
    DATA_TOKENS,
    DOMAIN,
)

from .conftest import setup_entry


async def test_setup_and_unload(hass, salt_entry):
    await setup_entry(hass, salt_entry)
    assert salt_entry.state is ConfigEntryState.LOADED
    assert hass.data[DOMAIN][DATA_TOKENS][salt_entry.data[CONF_TOKEN]] == salt_entry.entry_id

    assert await hass.config_entries.async_unload(salt_entry.entry_id)
    await hass.async_block_till_done()
    assert salt_entry.state is ConfigEntryState.NOT_LOADED
    assert salt_entry.data[CONF_TOKEN] not in hass.data[DOMAIN][DATA_TOKENS]


async def test_two_entries_share_views(hass, salt_entry, chlorine_entry):
    await setup_entry(hass, salt_entry)
    await setup_entry(hass, chlorine_entry)
    tokens = hass.data[DOMAIN][DATA_TOKENS]
    assert len(tokens) == 2

    assert await hass.config_entries.async_unload(salt_entry.entry_id)
    await hass.async_block_till_done()
    assert len(hass.data[DOMAIN][DATA_TOKENS]) == 1


async def test_nothing_is_added_to_the_dashboards(hass, salt_entry, monkeypatch):
    """The integration ships no Lovelace resource of its own any more."""
    import homeassistant.components.frontend as frontend
    from homeassistant.setup import async_setup_component

    urls: list[str] = []
    monkeypatch.setattr(
        frontend, "add_extra_js_url", lambda _hass, url: urls.append(url), raising=False
    )
    assert await async_setup_component(hass, "lovelace", {})
    await setup_entry(hass, salt_entry)

    assert urls == []
    assert hass.data["lovelace"].resources.async_items() == []


async def test_an_old_card_resource_is_taken_back(hass, salt_entry):
    """Upgrading must not leave a resource pointing at a card that is gone."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data["lovelace"].resources
    await resources.async_get_info()  # force the collection to load
    await resources.async_create_item(
        {"res_type": "module", "url": "/pool_maintenance_tracker/card.js?v=0.53.0"}
    )
    await resources.async_create_item({"res_type": "module", "url": "/local/mine.js"})

    await setup_entry(hass, salt_entry)

    assert [item["url"] for item in resources.async_items()] == ["/local/mine.js"]
