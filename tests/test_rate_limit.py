"""Rate limiting tests."""

from custom_components.pool_maintenance_tracker.const import URL_LOG, URL_PAGE
from custom_components.pool_maintenance_tracker.http import RateLimiter

from .conftest import TEST_TOKEN, setup_entry


def test_rate_limiter_window():
    limiter = RateLimiter()
    for _ in range(5):
        assert limiter.allow("bucket", "key", 5, 60)
    assert not limiter.allow("bucket", "key", 5, 60)
    # independent keys are unaffected
    assert limiter.allow("bucket", "other", 5, 60)


async def test_post_ip_rate_limit(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()
    url = URL_LOG.format(token=TEST_TOKEN)

    for _ in range(10):
        response = await client.post(url, json={"categories": ["other"]})
        assert response.status == 200

    response = await client.post(url, json={"categories": ["other"]})
    assert response.status == 429
    assert (await response.json())["error"] == "rate_limited"


async def test_invalid_token_lockout(hass, salt_entry, hass_client_no_auth):
    await setup_entry(hass, salt_entry)
    client = await hass_client_no_auth()

    for _ in range(20):
        response = await client.get(URL_PAGE.format(token="guess"))
        assert response.status == 404

    response = await client.get(URL_PAGE.format(token="guess"))
    assert response.status == 429
    # valid token is still served
    response = await client.get(URL_PAGE.format(token=TEST_TOKEN))
    assert response.status == 200
