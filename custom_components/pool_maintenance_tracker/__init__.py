"""The Pool Maintenance Tracker integration."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

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
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import (
    EventStateChangedData,
    async_track_state_change_event,
)
from homeassistant.helpers.typing import ConfigType

from . import filter_pressure, health, maintenance
from .const import (
    CATEGORY_FILTER_WASH,
    CONF_LANGUAGE,
    CONF_LINKED_MODE,
    CONF_POOL_SYSTEM_ENTITY,
    CONF_PUMP_ENTITY,
    CONF_TOKEN,
    DATA_TOKENS,
    DEFAULT_LANGUAGE,
    DOMAIN,
    LINKED_MODE_MANUAL,
    LINKED_MODE_MIRROR,
    LINKED_SOURCES,
    LINKED_VALUE_KEYS,
    NUMBER_RANGES,
    signal_record,
)
from .http import _load_strings, async_register_views
from .maintenance import MaintenanceSession
from .modules import active_entity_keys, enabled_value_keys
from .reminders import ReminderEngine
from .tracker import PoolTracker
from .websocket import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

# Pools are added from the UI; there is nothing to configure in YAML.
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

PLATFORMS = [
    Platform.BINARY_SENSOR,
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
    reminders: ReminderEngine
    session: MaintenanceSession
    # Short-lived answers too expensive to recompute on every poll
    cache: dict[str, Any] = field(default_factory=dict)


type PoolConfigEntry = ConfigEntry[PoolRuntimeData]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Get the Lovelace card onto the dashboards as early as we can.

    The card URL is injected into the page Home Assistant serves, so a
    dashboard opened before it is registered never fetches the script and
    Lovelace reports "Custom element doesn't exist" until that page is
    reloaded. Component setup runs before any config entry, which is the
    earliest this integration gets a say.
    """
    hass.data.setdefault(DOMAIN, {DATA_TOKENS: {}})
    _async_register_services(hass)
    await _async_register_frontend(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: PoolConfigEntry) -> bool:
    """Set up a pool from a config entry."""
    domain_data = hass.data.setdefault(DOMAIN, {DATA_TOKENS: {}})

    tracker = PoolTracker(hass, entry.entry_id, entry.data[CONF_NAME])
    await tracker.async_load()
    reminders = ReminderEngine(hass, entry, tracker)
    session = MaintenanceSession(hass, entry, tracker)
    entry.runtime_data = PoolRuntimeData(tracker=tracker, reminders=reminders, session=session)

    domain_data[DATA_TOKENS][entry.data[CONF_TOKEN]] = entry.entry_id
    async_register_views(hass)
    await _async_register_frontend(hass)
    async_register_websocket_api(hass)
    # Warm the string cache in this pool's language: the logbook describer
    # is synchronous and reads it, and the page will want it anyway.
    await _load_strings(hass, entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE))

    _async_prune_stale_entities(hass, entry)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    reminders.async_start()
    session.async_start()

    if entry.options.get(CONF_LINKED_MODE, LINKED_MODE_MANUAL) == LINKED_MODE_MIRROR:
        _async_setup_linked_mirror(hass, entry, tracker)
    _async_setup_filter_pressure(hass, entry, tracker)
    health.async_setup_health(hass, entry)

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


DATA_FRONTEND_REGISTERED = "frontend_registered"
CARD_URL = f"/{DOMAIN}/card.js"


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve the Lovelace card and get it loaded by the dashboards.

    There are two ways to load a card and they fail differently. The
    frontend's extra-js list is baked into the app's HTML, which the
    service worker caches — so whether a given page load sees the card
    depends on the state of that cache, which is exactly the intermittent
    "Custom element doesn't exist" its users get. A Lovelace *resource*
    (what HACS registers) is fetched over the websocket every time a
    dashboard loads, cache or no cache. So: resource when Lovelace storage
    is available, extra-js only as the fallback (YAML mode, no Lovelace).
    """
    domain_data = hass.data[DOMAIN]
    if domain_data.get(DATA_FRONTEND_REGISTERED):
        return
    from pathlib import Path

    card = Path(__file__).parent / "frontend" / "card.js"
    try:
        from homeassistant.components.http import StaticPathConfig
        from homeassistant.loader import async_get_integration
    except ImportError:
        _LOGGER.warning("Home Assistant frontend unavailable; the pool card was not loaded")
        return

    try:
        await hass.http.async_register_static_paths([StaticPathConfig(CARD_URL, str(card), True)])
    except (RuntimeError, ValueError) as err:
        # Already served from an earlier setup in this session — harmless.
        _LOGGER.debug("Card already served at %s (%s)", CARD_URL, err)

    integration = await async_get_integration(hass, DOMAIN)
    versioned_url = f"{CARD_URL}?v={integration.version}"

    if await _async_register_lovelace_resource(hass, versioned_url):
        domain_data[DATA_FRONTEND_REGISTERED] = True
        _LOGGER.debug("Card registered as a Lovelace resource: %s", versioned_url)
        return

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, versioned_url)
    except Exception:
        _LOGGER.warning(
            "Could not add %s to the dashboards - the Pool Maintenance card will show "
            "'Custom element does not exist'",
            CARD_URL,
            exc_info=True,
        )
        return
    domain_data[DATA_FRONTEND_REGISTERED] = True
    _LOGGER.debug("Card registered via extra_js_url (Lovelace storage unavailable)")


async def _async_register_lovelace_resource(hass: HomeAssistant, url: str) -> bool:
    """Point a Lovelace resource entry at the current card version.

    One entry, updated in place on version changes — including an entry the
    user once added by hand for the same path. Returns False when Lovelace
    is absent or its resources are YAML-managed, and the caller falls back.
    """
    lovelace = hass.data.get("lovelace")
    resources = getattr(lovelace, "resources", None)
    if resources is None or not hasattr(resources, "async_create_item"):
        return False
    try:
        if not resources.loaded:
            await resources.async_load()
            resources.loaded = True
        for item in resources.async_items():
            if str(item.get("url", "")).split("?")[0] == CARD_URL:
                if item["url"] != url:
                    await resources.async_update_item(item["id"], {"url": url})
                return True
        await resources.async_create_item({"res_type": "module", "url": url})
    except Exception:
        _LOGGER.warning("Could not manage the Lovelace resource for %s", CARD_URL, exc_info=True)
        return False
    return True


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
def _async_setup_filter_pressure(
    hass: HomeAssistant, entry: PoolConfigEntry, tracker: PoolTracker
) -> None:
    """Let the filter's pressure gauge drive its wash alert.

    Two hooks: every logged filter wash re-captures the clean baseline, and
    every pressure reading is judged against it. Both are no-ops without a
    linked sensor, which is how the fixed interval keeps working for
    everybody else.
    """

    @callback
    def _handle_record(record: dict) -> None:
        if CATEGORY_FILTER_WASH in record.get("categories", []):
            filter_pressure.async_capture_baseline(hass, entry, tracker)

    entry.async_on_unload(
        async_dispatcher_connect(hass, signal_record(entry.entry_id), _handle_record)
    )

    entity_id = filter_pressure.source_entity(entry)
    if not entity_id:
        return

    @callback
    def _handle_change(event: Event[EventStateChangedData]) -> None:
        filter_pressure.async_evaluate(hass, entry, tracker)

    # The pump switching on changes what the gauge means, so watch it too.
    watched = [entity_id]
    for conf_key in (CONF_PUMP_ENTITY, CONF_POOL_SYSTEM_ENTITY):
        if role_entity := entry.options.get(conf_key):
            watched.append(role_entity)

    filter_pressure.async_evaluate(hass, entry, tracker)
    entry.async_on_unload(async_track_state_change_event(hass, watched, _handle_change))


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
    entry.runtime_data.session.async_stop()
    tokens: dict[str, str] = hass.data[DOMAIN][DATA_TOKENS]
    for token, entry_id in list(tokens.items()):
        if entry_id == entry.entry_id:
            del tokens[token]
    await entry.runtime_data.tracker.async_flush()
    return True


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the stored state when the entry is removed."""
    health.async_remove_issues(hass, entry)
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
