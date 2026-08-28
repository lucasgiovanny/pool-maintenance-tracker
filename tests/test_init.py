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


async def test_the_lovelace_card_is_served_and_registered(
    hass, salt_entry, hass_client_no_auth, monkeypatch
):
    """The card failing to register used to be silent and invisible."""
    import homeassistant.components.frontend as frontend

    urls: list[str] = []
    monkeypatch.setattr(
        frontend, "add_extra_js_url", lambda _hass, url: urls.append(url), raising=False
    )

    await setup_entry(hass, salt_entry)

    for card in ("card.js", "scene-card.js"):
        assert any(url.startswith(f"/pool_maintenance_tracker/{card}?v=") for url in urls)

    client = await hass_client_no_auth()
    response = await client.get("/pool_maintenance_tracker/card.js")
    assert response.status == 200
    body = await response.text()
    assert 'customElements.define("pool-maintenance-card"' in body

    response = await client.get("/pool_maintenance_tracker/scene-card.js")
    assert response.status == 200
    body = await response.text()
    assert 'customElements.define("pool-scene-card"' in body


async def test_the_scene_photo_is_served(hass, salt_entry, hass_client_no_auth):
    """The scene card draws on a photo we ship; a 404 there is a blank card."""
    await setup_entry(hass, salt_entry)

    client = await hass_client_no_auth()
    response = await client.get("/pool_maintenance_tracker/scene/pool.jpg")
    assert response.status == 200
    assert response.content_type == "image/jpeg"


async def test_the_cards_become_lovelace_resources(hass, salt_entry, hass_client_no_auth):
    """A resource is fetched on every dashboard load; extra-js lives in the
    app HTML, which the service worker caches — the source of the
    intermittent "custom element doesn't exist"."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    await setup_entry(hass, salt_entry)

    resources = hass.data["lovelace"].resources
    urls = {item["url"].split("?")[0]: item for item in resources.async_items()}
    assert set(urls) == {
        "/pool_maintenance_tracker/card.js",
        "/pool_maintenance_tracker/scene-card.js",
    }
    for base, item in urls.items():
        assert item["url"].startswith(f"{base}?v=")
        assert item["type"] == "module"

    # the files behind the resources actually resolve
    client = await hass_client_no_auth()
    for base in urls:
        assert (await client.get(base)).status == 200


async def test_an_existing_resource_is_updated_not_duplicated(hass, salt_entry):
    """Covers both an old version's entry and one the user added by hand."""
    from homeassistant.setup import async_setup_component

    assert await async_setup_component(hass, "lovelace", {})
    resources = hass.data["lovelace"].resources
    await resources.async_get_info()  # force the collection to load
    await resources.async_create_item(
        {"res_type": "module", "url": "/pool_maintenance_tracker/card.js?v=0.1.0"}
    )

    await setup_entry(hass, salt_entry)

    items = resources.async_items()
    assert len(items) == 2
    stale = [item for item in items if item["url"].endswith("v=0.1.0")]
    assert not stale
