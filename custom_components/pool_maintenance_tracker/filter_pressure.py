"""Filter wash alerts driven by pressure instead of the calendar.

A sand or cartridge filter does not clog on a schedule — it clogs when it
clogs, and the filter tells you so by pushing the pressure up. The real
criterion is a rise over the pressure the filter showed when it was clean.

So: when a pressure sensor is linked and we know the clean baseline, that
rules the filter wash alert. Without either, nothing changes and the fixed
interval keeps working.

The clean baseline is captured automatically the moment somebody logs a
filter wash — that reading *is* the clean pressure, no extra question asked.
Readings taken with the pump off are worthless (the gauge falls to zero), so
they are ignored on both sides: we neither store them as a baseline nor let
them clear an alert.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_FILTER_PRESSURE_RISE,
    CONF_FILTER_PRESSURE_SOURCE,
    CONF_POOL_SYSTEM_ENTITY,
    CONF_PUMP_ENTITY,
    DEFAULT_FILTER_PRESSURE_RISE,
    METRIC_CLEAN_PRESSURE,
    METRIC_CLEAN_PRESSURE_AT,
    METRIC_PRESSURE_DUE,
    MIN_MEANINGFUL_PRESSURE,
    UNAVAILABLE_STATES,
    equipment_on,
)

if TYPE_CHECKING:
    from .tracker import PoolTracker

_LOGGER = logging.getLogger(__name__)


@callback
def source_entity(entry: ConfigEntry) -> str | None:
    return entry.options.get(CONF_FILTER_PRESSURE_SOURCE) or None


@callback
def _reading(hass: HomeAssistant, entity_id: str) -> tuple[float | None, str]:
    """Current pressure and its unit, or (None, "") when unusable."""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable", ""):
        return None, ""
    try:
        return float(state.state), state.attributes.get("unit_of_measurement", "")
    except (TypeError, ValueError):
        return None, ""


@callback
def _pump_running(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Whether the water is moving, as far as we can tell.

    With no pump or system entity configured we have to trust the sensor:
    saying "not running" would silence the alert forever.
    """
    for conf_key in (CONF_PUMP_ENTITY, CONF_POOL_SYSTEM_ENTITY):
        entity_id = entry.options.get(conf_key)
        if not entity_id:
            continue
        state = hass.states.get(entity_id)
        if state is None or state.state in UNAVAILABLE_STATES:
            continue
        return equipment_on(entity_id.split(".")[0], state.state) is True
    return True


@callback
def threshold(entry: ConfigEntry) -> float:
    """Pressure rise, as a fraction, that means "wash the filter"."""
    percent = entry.options.get(CONF_FILTER_PRESSURE_RISE, DEFAULT_FILTER_PRESSURE_RISE)
    return float(percent) / 100


@callback
def async_capture_baseline(hass: HomeAssistant, entry: ConfigEntry, tracker: PoolTracker) -> None:
    """Remember the pressure of a freshly washed filter.

    Called when a filter wash is logged. A reading taken with the pump off
    would poison every later comparison, so it is dropped and the previous
    baseline stands.
    """
    entity_id = source_entity(entry)
    if not entity_id:
        return
    value, _unit = _reading(hass, entity_id)
    if value is None or value < MIN_MEANINGFUL_PRESSURE or not _pump_running(hass, entry):
        _LOGGER.debug("Filter wash logged but %s did not give a usable clean baseline", entity_id)
        return
    from homeassistant.util import dt as dt_util

    tracker.metrics[METRIC_CLEAN_PRESSURE] = value
    tracker.metrics[METRIC_CLEAN_PRESSURE_AT] = dt_util.utcnow().isoformat()
    tracker.metrics[METRIC_PRESSURE_DUE] = False
    tracker.async_save()
    tracker.async_update_listeners()


@callback
def async_evaluate(hass: HomeAssistant, entry: ConfigEntry, tracker: PoolTracker) -> None:
    """Re-judge the filter from the current pressure, if that is meaningful.

    The verdict is persisted rather than recomputed on demand: when the pump
    stops, the gauge drops and the last verdict taken under flow is the only
    honest answer we have.
    """
    entity_id = source_entity(entry)
    clean = tracker.metrics.get(METRIC_CLEAN_PRESSURE)
    if not entity_id or not clean:
        return
    value, _unit = _reading(hass, entity_id)
    if value is None or value < MIN_MEANINGFUL_PRESSURE or not _pump_running(hass, entry):
        return
    due = value >= clean * (1 + threshold(entry))
    if due != tracker.metrics.get(METRIC_PRESSURE_DUE):
        tracker.metrics[METRIC_PRESSURE_DUE] = due
        tracker.async_save()
        tracker.async_update_listeners()


@callback
def rules_the_alert(entry: ConfigEntry, tracker: PoolTracker) -> bool:
    """True when pressure decides the filter wash alert instead of the date."""
    return bool(source_entity(entry) and tracker.metrics.get(METRIC_CLEAN_PRESSURE))


@callback
def is_due(entry: ConfigEntry, tracker: PoolTracker) -> bool | None:
    """Pressure verdict, or None when pressure has nothing to say."""
    if not rules_the_alert(entry, tracker):
        return None
    return bool(tracker.metrics.get(METRIC_PRESSURE_DUE))


@callback
def snapshot(
    hass: HomeAssistant, entry: ConfigEntry, tracker: PoolTracker
) -> dict[str, Any] | None:
    """What the surfaces show about the filter's pressure."""
    entity_id = source_entity(entry)
    if not entity_id:
        return None
    value, unit = _reading(hass, entity_id)
    clean = tracker.metrics.get(METRIC_CLEAN_PRESSURE)
    rise = None
    if value is not None and clean:
        rise = round((value / clean - 1) * 100)
    return {
        "entity_id": entity_id,
        "value": value,
        "unit": unit,
        "clean": clean,
        "clean_at": tracker.metrics.get(METRIC_CLEAN_PRESSURE_AT),
        "rise_percent": rise,
        "threshold_percent": round(threshold(entry) * 100),
        "due": is_due(entry, tracker),
    }
