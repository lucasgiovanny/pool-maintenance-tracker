"""WebSocket API feeding the custom Lovelace card."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_call_later

from .const import DEFAULT_LANGUAGE, DOMAIN, LANGUAGES, signal_updated
from .entity import page_url

WS_STATUS = f"{DOMAIN}/status"
WS_POOLS = f"{DOMAIN}/pools"
WS_SUBSCRIBE = f"{DOMAIN}/subscribe"

# One logged record moves a dozen things at once; ship one event, not twelve.
PUSH_DEBOUNCE = 0.3


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the card's WebSocket commands once."""
    websocket_api.async_register_command(hass, ws_pools)
    websocket_api.async_register_command(hass, ws_status)
    websocket_api.async_register_command(hass, ws_subscribe)


@callback
@websocket_api.websocket_command({vol.Required("type"): WS_POOLS})
def ws_pools(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """List the loaded pools so the card can pick one by itself."""
    connection.send_result(
        msg["id"],
        [
            {"entry_id": entry.entry_id, "title": entry.title}
            for entry in hass.config_entries.async_entries(DOMAIN)
            if entry.state is ConfigEntryState.LOADED
        ],
    )


@callback
def _resolve(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> tuple[ConfigEntry, str] | None:
    """The entry and display language for a card request, or None + error.

    The page speaks the language configured for the pool; the card lives
    inside Home Assistant, so it follows the language of whoever is looking
    at it (falling back to English when we don't ship it).
    """
    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "Unknown or unloaded pool")
        return None
    requested = (msg.get("language") or entry.options.get("language", "en")).lower()
    # "pt-br" is its own bundle; any other region falls back to its base.
    for candidate in (requested, requested.split("-")[0]):
        if candidate in LANGUAGES:
            return entry, candidate
    return entry, DEFAULT_LANGUAGE


async def _status_payload(hass: HomeAssistant, entry: ConfigEntry, language: str) -> dict[str, Any]:
    """Everything the card needs to render one pool."""
    from .http import _load_strings
    from .report import _build_report, _live_values

    return {
        "entry_id": entry.entry_id,
        "title": entry.title,
        "language": language,
        "strings": await _load_strings(hass, language),
        "live": _live_values(hass, entry),
        "report": await _build_report(hass, entry),
        "page_url": page_url(hass, entry),
    }


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_STATUS,
        vol.Required("entry_id"): str,
        vol.Optional("language"): str,
    }
)
@websocket_api.async_response
async def ws_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """One-shot status, for the card's poll fallback."""
    if (resolved := _resolve(hass, connection, msg)) is None:
        return
    entry, language = resolved
    connection.send_result(msg["id"], await _status_payload(hass, entry, language))


@websocket_api.websocket_command(
    {
        vol.Required("type"): WS_SUBSCRIBE,
        vol.Required("entry_id"): str,
        vol.Optional("language"): str,
    }
)
@websocket_api.async_response
async def ws_subscribe(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Status now, and again every time the tracker changes.

    This is what lets the card stop polling: a record, an edited value or
    the maintenance flag land as an event within the debounce window
    instead of on the next 30-second tick.
    """
    if (resolved := _resolve(hass, connection, msg)) is None:
        return
    entry, language = resolved
    timer: list[CALLBACK_TYPE | None] = [None]

    async def _push(_now: Any = None) -> None:
        timer[0] = None
        if entry.state is not ConfigEntryState.LOADED:
            return
        payload = await _status_payload(hass, entry, language)
        connection.send_message(websocket_api.event_message(msg["id"], payload))

    @callback
    def _schedule() -> None:
        if timer[0] is None:
            timer[0] = async_call_later(hass, PUSH_DEBOUNCE, _push)

    unsub_signal = async_dispatcher_connect(hass, signal_updated(entry.entry_id), _schedule)

    @callback
    def _unsubscribe() -> None:
        unsub_signal()
        if timer[0] is not None:
            timer[0]()
            timer[0] = None

    connection.subscriptions[msg["id"]] = _unsubscribe
    connection.send_result(msg["id"])
    await _push()
