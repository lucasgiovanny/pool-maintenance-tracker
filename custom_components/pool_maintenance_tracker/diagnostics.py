"""Diagnostics support for Pool Maintenance Tracker."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import CONF_TOKEN

if TYPE_CHECKING:
    from . import PoolConfigEntry

TO_REDACT = {CONF_TOKEN}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: PoolConfigEntry
) -> dict[str, Any]:
    tracker = entry.runtime_data.tracker
    return {
        "entry": {
            "data": async_redact_data(dict(entry.data), TO_REDACT),
            "options": dict(entry.options),
        },
        "state": {
            "values": tracker.values,
            "values_at": tracker.values_at,
            "timestamps": tracker.timestamps,
            "installed_at": tracker.installed_at,
            "records_count": len(tracker.records),
            "maintenance_mode": tracker.maintenance_mode,
            "maintenance_mode_at": tracker.maintenance_mode_at,
            "maintenance_mode_by": tracker.maintenance_mode_by,
        },
    }
