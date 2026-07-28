"""WebSocket API feeding the custom Lovelace card."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .entity import page_url

WS_STATUS = f"{DOMAIN}/status"
WS_POOLS = f"{DOMAIN}/pools"


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register the card's WebSocket commands once."""
    websocket_api.async_register_command(hass, ws_pools)
    websocket_api.async_register_command(hass, ws_status)


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


@websocket_api.websocket_command({vol.Required("type"): WS_STATUS, vol.Required("entry_id"): str})
@websocket_api.async_response
async def ws_status(
    hass: HomeAssistant, connection: websocket_api.ActiveConnection, msg: dict[str, Any]
) -> None:
    """Everything the card needs to render one pool."""
    from .http import _build_report, _live_values, _load_strings

    entry = hass.config_entries.async_get_entry(msg["entry_id"])
    if entry is None or entry.domain != DOMAIN or entry.state is not ConfigEntryState.LOADED:
        connection.send_error(msg["id"], "not_found", "Unknown or unloaded pool")
        return

    language = entry.options.get("language", "en")
    connection.send_result(
        msg["id"],
        {
            "entry_id": entry.entry_id,
            "title": entry.title,
            "language": language,
            "strings": await _load_strings(hass, language),
            "live": _live_values(hass, entry),
            "report": await _build_report(hass, entry),
            "page_url": page_url(hass, entry),
        },
    )
