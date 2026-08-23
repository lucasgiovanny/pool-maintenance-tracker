"""Describe maintenance records on the Home Assistant logbook.

Every accepted record already fires ``pool_maintenance_tracker_record`` on
the bus; this turns it into a sentence on the native timeline — who, and
what they did — in the language the pool's page speaks.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from homeassistant.core import Event, HomeAssistant, callback

from .const import (
    CONF_LANGUAGE,
    DATA_STRINGS_CACHE,
    DEFAULT_LANGUAGE,
    DOMAIN,
    EVENT_RECORD,
)


@callback
def async_describe_events(
    hass: HomeAssistant,
    async_describe_event: Callable[[str, str, Callable[[Event], dict[str, str]]], None],
) -> None:
    """Register the describer for the record event."""

    @callback
    def _describe(event: Event) -> dict[str, str]:
        strings = _strings_for(hass, event.data.get("entry_id"))
        tiles = strings.get("tiles", {})
        labels = strings.get("report", {}).get("values", {})
        what = ", ".join(tiles.get(key, key) for key in event.data.get("categories") or [])
        if not what:
            # A record can be readings alone; name what was measured.
            what = ", ".join(labels.get(key, key) for key in event.data.get("data") or {})
        person = event.data.get("person") or "?"
        return {
            "name": event.data.get("pool_name") or "Pool",
            "message": f"{person} · {what}" if what else person,
        }

    async_describe_event(DOMAIN, EVENT_RECORD, _describe)


@callback
def _strings_for(hass: HomeAssistant, entry_id: Any) -> dict[str, Any]:
    """The page-language string bundle, from the cache the views keep.

    The bundle is preloaded at entry setup, so by the time a record can
    fire the cache is warm; an empty dict just means raw keys in the
    message, never an error.
    """
    language = DEFAULT_LANGUAGE
    if entry_id and (entry := hass.config_entries.async_get_entry(str(entry_id))):
        language = entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
    cache = hass.data.get(DOMAIN, {}).get(DATA_STRINGS_CACHE, {})
    return cache.get(language) or cache.get(DEFAULT_LANGUAGE) or {}
