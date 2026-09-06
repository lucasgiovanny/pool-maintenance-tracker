"""The Pool Maintenance Tracker integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Final

import voluptuous as vol
from homeassistant.config_entries import ConfigEntry, ConfigEntryState
from homeassistant.const import CONF_NAME, Platform
from homeassistant.core import (
    Event,
    HomeAssistant,
    ServiceCall,
    SupportsResponse,
    callback,
)
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)
from homeassistant.helpers.typing import ConfigType

from . import maintenance
from .const import (
    CONF_LANGUAGE,
    CONF_LINKED_MODE,
    CONF_TOKEN,
    DATA_TOKENS,
    DEFAULT_LANGUAGE,
    DOMAIN,
    LINKED_MODE_MANUAL,
    LINKED_MODE_MIRROR,
    LINKED_SOURCES,
    LINKED_VALUE_KEYS,
    NUMBER_RANGES,
)
from .http import _load_strings, async_register_views
from .maintenance import MaintenanceSession
from .modules import active_entity_keys, enabled_value_keys
from .tracker import PoolTracker

_LOGGER = logging.getLogger(__name__)

# Pools are added from the UI; there is nothing to configure in YAML.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.EVENT,
    Platform.IMAGE,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


@dataclass
class PoolRuntimeData:
    """Runtime objects for one pool entry."""

    tracker: PoolTracker
    session: MaintenanceSession
    # Short-lived answers too expensive to recompute on every poll
    cache: dict[str, Any] = field(default_factory=dict)


type PoolConfigEntry = ConfigEntry[PoolRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions before any pool is loaded."""
    hass.data.setdefault(DOMAIN, {DATA_TOKENS: {}})
    _async_register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PoolConfigEntry) -> bool:
    """Set up a pool from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {DATA_TOKENS: {}})

    tracker = PoolTracker(hass, entry.entry_id, entry.data[CONF_NAME])
    await tracker.async_load()
    session = MaintenanceSession(hass, entry, tracker)
    entry.runtime_data = PoolRuntimeData(tracker=tracker, session=session)

    domain_data[DATA_TOKENS][entry.data[CONF_TOKEN]] = entry.entry_id
    async_register_views(hass)
    await _async_drop_card_resources(hass)
    # Warm the string cache in this pool's language: the logbook describer
    # is synchronous and reads it, and the page will want it anyway.
    await _load_strings(hass, entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE))

    _async_prune_stale_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    session.async_start()

    if entry.options.get(CONF_LINKED_MODE, LINKED_MODE_MANUAL) == LINKED_MODE_MIRROR:
        _async_setup_linked_mirror(hass, entry, tracker)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


DATA_CARDS_DROPPED = "cards_dropped"
# The Lovelace resources earlier versions registered for the cards they used
# to ship. The cards are gone; an entry left pointing at them is a 404 on
# every dashboard load, so this takes back what the integration put there.
OLD_CARD_URLS: Final[tuple[str, ...]] = (
    f"/{DOMAIN}/card.js",
    f"/{DOMAIN}/scene-card.js",
)


async def _async_drop_card_resources(hass: HomeAssistant) -> None:
    """Remove the card resources this integration used to register."""
    domain_data = hass.data[DOMAIN]
    if domain_data.get(DATA_CARDS_DROPPED):
        return
    domain_data[DATA_CARDS_DROPPED] = True
    resources = getattr(hass.data.get("lovelace"), "resources", None)
    if resources is None or not hasattr(resources, "async_delete_item"):
        return
    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        for item in list(resources.async_items()):
            if str(item.get("url", "")).split("?")[0] in OLD_CARD_URLS:
                await resources.async_delete_item(item["id"])
                _LOGGER.debug("Removed the stale Lovelace resource %s", item["url"])
    except Exception:
        _LOGGER.debug("Could not tidy up the old card resources", exc_info=True)


SERVICE_DELETE_RECORD = "delete_record"
DELETE_RECORD_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry"): str,
        vol.Optional("record_id"): str,
    }
)

SERVICE_EXPORT_RECORDS = "export_records"
EXPORT_RECORDS_SCHEMA = vol.Schema({vol.Required("config_entry"): str})

SERVICE_START_MAINTENANCE = "start_maintenance"
START_MAINTENANCE_SCHEMA = vol.Schema(
    {
        vol.Required("config_entry"): str,
        vol.Optional("minutes"): vol.Any(None, vol.Coerce(int)),
        vol.Optional("equipment"): {cv.string: cv.string},
    }
)


def _pool_entry(hass: HomeAssistant, entry_id: str) -> PoolConfigEntry:
    entry = hass.config_entries.async_get_entry(entry_id)
    if entry is None or entry.domain != DOMAIN:
        raise ServiceValidationError(
            "Unknown Pool Maintenance Tracker entry",
            translation_domain=DOMAIN,
            translation_key="unknown_entry",
        )
    if entry.state is not ConfigEntryState.LOADED:
        raise ServiceValidationError(
            "The pool is not loaded",
            translation_domain=DOMAIN,
            translation_key="not_loaded",
        )
    return entry


@callback
def _async_register_services(hass: HomeAssistant) -> None:
    """Register the actions. Called from async_setup: an action must exist
    (and answer with a proper error) even while no pool is loaded."""

    async def _handle_delete_record(call: ServiceCall) -> None:
        entry = _pool_entry(hass, call.data["config_entry"])
        if not entry.runtime_data.tracker.async_delete_record(call.data.get("record_id")):
            raise ServiceValidationError(
                "No matching record to delete",
                translation_domain=DOMAIN,
                translation_key="no_record",
            )

    async def _handle_start_maintenance(call: ServiceCall) -> None:
        """Raise the flag with a window and a plan, the way the page does.

        switch.turn_on cannot carry either, so this is how a dashboard
        button, an NFC tag or another automation starts a timed visit.
        Dropping it early is still switch.turn_off.
        """
        entry = _pool_entry(hass, call.data["config_entry"])
        if not maintenance.is_enabled(entry):
            raise ServiceValidationError(
                "Maintenance mode is switched off for this pool",
                translation_domain=DOMAIN,
                translation_key="maintenance_disabled",
            )
        try:
            until = maintenance.parse_minutes(call.data.get("minutes"))
            plan, ignored = maintenance.clean_plan(hass, entry, call.data.get("equipment"))
        except maintenance.PlanError as err:
            raise ServiceValidationError(
                str(err),
                translation_domain=DOMAIN,
                translation_key="invalid_plan",
                translation_placeholders={"reason": str(err)},
            ) from err
        if ignored:
            _LOGGER.warning("start_maintenance ignored %s for %s", ", ".join(ignored), entry.title)
        entry.runtime_data.tracker.async_set_maintenance_mode(True, until=until, plan=plan)
        await maintenance.async_apply(hass, entry, plan)

    hass.services.async_register(
        DOMAIN,
        SERVICE_DELETE_RECORD,
        _handle_delete_record,
        schema=DELETE_RECORD_SCHEMA,
    )

    async def _handle_export_records(call: ServiceCall) -> dict[str, Any]:
        """The whole log, handed back as response data.

        The tracker's Store caps what it keeps; this is how the data leaves
        the house whole — into an automation, a script, or a file of the
        owner's choosing.
        """
        entry = _pool_entry(hass, call.data["config_entry"])
        tracker = entry.runtime_data.tracker
        return {
            "pool": entry.title,
            "records": list(tracker.records),
            "notes": list(tracker.notes),
        }

    hass.services.async_register(
        DOMAIN,
        SERVICE_START_MAINTENANCE,
        _handle_start_maintenance,
        schema=START_MAINTENANCE_SCHEMA,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_EXPORT_RECORDS,
        _handle_export_records,
        schema=EXPORT_RECORDS_SCHEMA,
        supports_response=SupportsResponse.ONLY,
    )


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
    entry.runtime_data.session.async_stop()
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
