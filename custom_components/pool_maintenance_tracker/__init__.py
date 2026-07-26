"""The Pool Maintenance Tracker integration."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)

from .const import (
    CONF_LINKED_MODE,
    CONF_TOKEN,
    DATA_TOKENS,
    DOMAIN,
    LINKED_MODE_MANUAL,
    LINKED_MODE_MIRROR,
    LINKED_SOURCES,
    LINKED_VALUE_KEYS,
    NUMBER_RANGES,
)
from .http import async_register_views
from .modules import active_entity_keys, enabled_value_keys
from .reminders import ReminderEngine
from .tracker import PoolTracker

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.EVENT,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
]


@dataclass
class PoolRuntimeData:
    """Runtime objects for one pool entry."""

    tracker: PoolTracker
    reminders: ReminderEngine


type PoolConfigEntry = ConfigEntry[PoolRuntimeData]


async def async_setup_entry(hass: HomeAssistant, entry: PoolConfigEntry) -> bool:
    """Set up a pool from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {DATA_TOKENS: {}})

    tracker = PoolTracker(hass, entry.entry_id, entry.data[CONF_NAME])
    await tracker.async_load()
    reminders = ReminderEngine(hass, entry, tracker)
    entry.runtime_data = PoolRuntimeData(tracker=tracker, reminders=reminders)

    domain_data[DATA_TOKENS][entry.data[CONF_TOKEN]] = entry.entry_id
    async_register_views(hass)

    _async_prune_stale_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    reminders.async_start()

    if entry.options.get(CONF_LINKED_MODE, LINKED_MODE_MANUAL) == LINKED_MODE_MIRROR:
        _async_setup_linked_mirror(hass, entry, tracker)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


@callback
def _async_setup_linked_mirror(
    hass: HomeAssistant, entry: PoolConfigEntry, tracker: PoolTracker
) -> None:
    """Keep manual entities in sync with the linked sensors (mirror mode)."""
    mapping: dict[str, str] = {}
    value_keys = enabled_value_keys(entry.options)
    for live_key, conf_key in LINKED_SOURCES.items():
        entity_id = entry.options.get(conf_key)
        value_key = LINKED_VALUE_KEYS.get(live_key)
        if entity_id and value_key and value_key in value_keys:
            mapping[entity_id] = value_key

    if not mapping:
        return

    @callback
    def _apply(entity_id: str) -> None:
        state = hass.states.get(entity_id)
        if state is None:
            return
        try:
            value = float(state.state)
        except ValueError:
            return
        value_key = mapping[entity_id]
        minimum, maximum, _step = NUMBER_RANGES[value_key]
        if minimum <= value <= maximum:
            tracker.async_set_value(value_key, round(value, 2))

    @callback
    def _handle_change(event: Event[EventStateChangedData]) -> None:
        _apply(event.data["entity_id"])

    for entity_id in mapping:
        _apply(entity_id)
    entry.async_on_unload(async_track_state_change_event(hass, list(mapping), _handle_change))


async def async_unload_entry(hass: HomeAssistant, entry: PoolConfigEntry) -> bool:
    """Unload a pool entry."""
    if not await hass.config_entries.async_unload_platforms(entry, PLATFORMS):
        return False
    entry.runtime_data.reminders.async_stop()
    tokens: dict[str, str] = hass.data[DOMAIN][DATA_TOKENS]
    for token, entry_id in list(tokens.items()):
        if entry_id == entry.entry_id:
            del tokens[token]
    await entry.runtime_data.tracker.async_flush()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the stored state when the entry is removed."""
    tracker = PoolTracker(hass, entry.entry_id, entry.data.get(CONF_NAME, ""))
    await tracker.async_remove_storage()


async def _async_update_listener(hass: HomeAssistant, entry: PoolConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)


def _async_prune_stale_entities(hass: HomeAssistant, entry: PoolConfigEntry) -> None:
    """Remove registry entries for entities of disabled modules."""
    registry = er.async_get(hass)
    active_unique_ids = {f"{entry.entry_id}_{key}" for key in active_entity_keys(entry.options)}
    for reg_entry in er.async_entries_for_config_entry(registry, entry.entry_id):
        if reg_entry.unique_id not in active_unique_ids:
            registry.async_remove(reg_entry.entity_id)
