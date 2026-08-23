"""Repair issues for configuration that points at nothing.

Every entity id in the options was picked from a live list, but nothing
stops its owner integration from being removed, or the entity from being
renamed, later. When that happens the tracker's surfaces just stop showing
the row — silently, which reads as a bug in *this* integration. A repair
issue names the missing entity and where it was configured, and clears
itself the moment the entity comes back.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, Event, HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir

from .const import (
    CONF_FILTER_PRESSURE_SOURCE,
    CONF_REPORT_SENSORS,
    DOMAIN,
    EQUIPMENT_ROLES,
    LINKED_SOURCES,
    SCHEDULE_TIME_KEYS,
)

if TYPE_CHECKING:
    from . import PoolConfigEntry

SINGLE_KEYS: tuple[str, ...] = (
    *EQUIPMENT_ROLES.values(),
    *SCHEDULE_TIME_KEYS,
    *LINKED_SOURCES.values(),
    CONF_FILTER_PRESSURE_SOURCE,
)


@callback
def _configured_entities(entry: PoolConfigEntry) -> dict[str, str]:
    """issue-id suffix -> entity id, for everything the options point at."""
    configured = {
        conf_key: entity_id
        for conf_key in SINGLE_KEYS
        if (entity_id := entry.options.get(conf_key))
    }
    for entity_id in entry.options.get(CONF_REPORT_SENSORS, ()):
        configured[f"report_{entity_id}"] = entity_id
    return configured


@callback
def _exists(hass: HomeAssistant, entity_id: str) -> bool:
    """Whether anything still answers to this id.

    The registry survives restarts, so an entity from a not-yet-loaded
    integration is still found there; a state covers the handful of
    entities that never register.
    """
    return (
        er.async_get(hass).async_get(entity_id) is not None
        or hass.states.get(entity_id) is not None
    )


@callback
def _issue_id(entry: PoolConfigEntry, suffix: str) -> str:
    return f"missing_{entry.entry_id}_{suffix}"


@callback
def _check(hass: HomeAssistant, entry: PoolConfigEntry) -> None:
    """Raise an issue per dangling reference; clear the ones that healed."""
    for suffix, entity_id in _configured_entities(entry).items():
        if _exists(hass, entity_id):
            ir.async_delete_issue(hass, DOMAIN, _issue_id(entry, suffix))
            continue
        ir.async_create_issue(
            hass,
            DOMAIN,
            _issue_id(entry, suffix),
            is_fixable=False,
            severity=ir.IssueSeverity.WARNING,
            translation_key="missing_entity",
            translation_placeholders={"pool": entry.title, "entity_id": entity_id},
        )


@callback
def async_setup_health(hass: HomeAssistant, entry: PoolConfigEntry) -> None:
    """Watch the configured references for as long as the entry lives.

    The full check waits for Home Assistant to be running: at boot the
    states are still filling in, and a warning that clears itself two
    seconds later only teaches people to ignore warnings.
    """

    @callback
    def _on_registry_update(event: Event[er.EventEntityRegistryUpdatedData]) -> None:
        _check(hass, entry)

    @callback
    def _concerns_us(data: er.EventEntityRegistryUpdatedData) -> bool:
        return data["entity_id"] in tracked or data.get("old_entity_id") in tracked

    tracked = set(_configured_entities(entry).values())
    if tracked:
        entry.async_on_unload(
            hass.bus.async_listen(
                er.EVENT_ENTITY_REGISTRY_UPDATED,
                _on_registry_update,
                event_filter=_concerns_us,
            )
        )

    if hass.state is CoreState.running:
        _check(hass, entry)
        return

    @callback
    def _on_started(event: Event) -> None:
        _check(hass, entry)

    entry.async_on_unload(hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _on_started))


@callback
def async_remove_issues(hass: HomeAssistant, entry: PoolConfigEntry) -> None:
    """Drop every issue this entry ever raised (entry removal)."""
    registry = ir.async_get(hass)
    prefix = f"missing_{entry.entry_id}_"
    for domain, issue_id in list(registry.issues):
        if domain == DOMAIN and issue_id.startswith(prefix):
            ir.async_delete_issue(hass, DOMAIN, issue_id)
