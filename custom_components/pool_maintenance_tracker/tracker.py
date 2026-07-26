"""Store-backed declarative state for one pool config entry.

The tracker is the single authority for values, timestamps and the record
log. Entities are thin views over it, notified through the dispatcher.
There is exactly one write path (``async_set_value`` / ``async_apply``),
used both by the public POST endpoint and by edits made in the HA UI.
Nothing here ever commands equipment.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    EVENT_RECORD,
    MAX_RECORDS,
    STORAGE_VERSION,
    signal_record,
    signal_updated,
)

if TYPE_CHECKING:
    from .processor import ProcessResult

SAVE_DELAY_SECONDS = 5.0


class PoolTracker:
    """Owns the maintenance state for one pool."""

    def __init__(self, hass: HomeAssistant, entry_id: str, pool_name: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.pool_name = pool_name
        self._store: Store[dict[str, Any]] = Store(hass, STORAGE_VERSION, f"{DOMAIN}.{entry_id}")
        self.values: dict[str, Any] = {}
        self.timestamps: dict[str, str] = {}
        self.last_record: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self.reminders_last_notified: dict[str, str] = {}
        self.installed_at: str = dt_util.utcnow().isoformat()

    async def async_load(self) -> None:
        """Load persisted state; initialize the install baseline on first run."""
        data = await self._store.async_load()
        if data is None:
            self.async_save()
            return
        self.values = data.get("values", {})
        self.timestamps = data.get("timestamps", {})
        self.last_record = data.get("last_record")
        self.records = data.get("records", [])
        self.reminders_last_notified = data.get("reminders_last_notified", {})
        self.installed_at = data.get("installed_at", self.installed_at)

    async def async_flush(self) -> None:
        """Write any pending state to disk immediately (used on unload)."""
        await self._store.async_save(self._data_to_save())

    async def async_remove_storage(self) -> None:
        """Delete the persisted state (used when the entry is removed)."""
        await self._store.async_remove()

    @callback
    def async_save(self) -> None:
        self._store.async_delay_save(self._data_to_save, SAVE_DELAY_SECONDS)

    def _data_to_save(self) -> dict[str, Any]:
        return {
            "values": self.values,
            "timestamps": self.timestamps,
            "last_record": self.last_record,
            "records": self.records,
            "reminders_last_notified": self.reminders_last_notified,
            "installed_at": self.installed_at,
        }

    def get_timestamp(self, key: str) -> datetime | None:
        raw = self.timestamps.get(key)
        return dt_util.parse_datetime(raw) if raw else None

    @property
    def installed_at_dt(self) -> datetime:
        return dt_util.parse_datetime(self.installed_at) or dt_util.utcnow()

    @callback
    def async_set_value(self, key: str, value: Any) -> None:
        """Set a declarative value (used by number/select entities in the UI)."""
        self.values[key] = value
        self.async_update_listeners()
        self.async_save()

    @callback
    def async_apply(self, result: ProcessResult) -> None:
        """Apply an accepted maintenance record and notify all consumers."""
        self.values.update(result.values)
        self.timestamps.update(result.timestamps)
        self.last_record = result.record
        self.records.append(result.record)
        del self.records[:-MAX_RECORDS]
        self.async_update_listeners()
        async_dispatcher_send(self.hass, signal_record(self.entry_id), result.record)
        self.hass.bus.async_fire(
            EVENT_RECORD,
            {"entry_id": self.entry_id, "pool_name": self.pool_name, **result.record},
        )
        self.async_save()

    @callback
    def async_update_listeners(self) -> None:
        async_dispatcher_send(self.hass, signal_updated(self.entry_id))
