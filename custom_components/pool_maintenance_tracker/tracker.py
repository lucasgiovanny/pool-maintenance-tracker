"""Store-backed declarative state for one pool config entry.

The tracker is the single authority for values, timestamps and the record
log. Entities are thin views over it, notified through the dispatcher.
There is exactly one write path (``async_set_value`` / ``async_apply``),
used both by the public POST endpoint and by edits made in the HA UI.
Nothing here ever commands equipment.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util
from homeassistant.util import ulid as ulid_util

from .const import (
    COMBINED_CHLORINE_WINDOW_HOURS,
    DOMAIN,
    EVENT_RECORD,
    KEY_FREE_CHLORINE,
    KEY_TOTAL_CHLORINE,
    MAX_NOTES,
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
        # When each value was last set — a manual reading and a probe both
        # claim to be "the" temperature, so freshness has to decide.
        self.values_at: dict[str, str] = {}
        self.timestamps: dict[str, str] = {}
        self.last_record: dict[str, Any] | None = None
        self.records: list[dict[str, Any]] = []
        self.notes: list[dict[str, Any]] = []
        self.reminders_last_notified: dict[str, str] = {}
        # Derived facts that are neither a reading nor a timestamp — today
        # just the filter's clean pressure and the verdict drawn from it.
        self.metrics: dict[str, Any] = {}
        # Maintenance mode: a flag, when it was last flipped, and by whom.
        # It survives restarts on purpose — a technician who raised it and
        # went home should not have it dropped by a Home Assistant update.
        self.maintenance_mode: bool = False
        self.maintenance_mode_at: str | None = None
        self.maintenance_mode_by: str | None = None
        # When the window closes (None = no limit), what the technician asked
        # the equipment to do, and where that equipment stood before they did.
        # The last one is what lets the window put things back.
        self.maintenance_mode_until: str | None = None
        self.maintenance_mode_plan: dict[str, str] = {}
        self.maintenance_mode_restore: dict[str, str] = {}
        self.installed_at: str = dt_util.utcnow().isoformat()

    async def async_load(self) -> None:
        """Load persisted state; initialize the install baseline on first run."""
        data = await self._store.async_load()
        if data is None:
            self.async_save()
            return
        self.values = data.get("values", {})
        self.values_at = data.get("values_at", {})
        self.timestamps = data.get("timestamps", {})
        self.last_record = data.get("last_record")
        self.records = data.get("records", [])
        self.notes = data.get("notes", [])
        self.reminders_last_notified = data.get("reminders_last_notified", {})
        self.metrics = data.get("metrics", {})
        self.maintenance_mode = bool(data.get("maintenance_mode", False))
        self.maintenance_mode_at = data.get("maintenance_mode_at")
        self.maintenance_mode_by = data.get("maintenance_mode_by")
        self.maintenance_mode_until = data.get("maintenance_mode_until")
        self.maintenance_mode_plan = data.get("maintenance_mode_plan", {})
        self.maintenance_mode_restore = data.get("maintenance_mode_restore", {})
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
            "values_at": self.values_at,
            "timestamps": self.timestamps,
            "last_record": self.last_record,
            "records": self.records,
            "notes": self.notes,
            "reminders_last_notified": self.reminders_last_notified,
            "metrics": self.metrics,
            "maintenance_mode": self.maintenance_mode,
            "maintenance_mode_at": self.maintenance_mode_at,
            "maintenance_mode_by": self.maintenance_mode_by,
            "maintenance_mode_until": self.maintenance_mode_until,
            "maintenance_mode_plan": self.maintenance_mode_plan,
            "maintenance_mode_restore": self.maintenance_mode_restore,
            "installed_at": self.installed_at,
        }

    def get_timestamp(self, key: str) -> datetime | None:
        raw = self.timestamps.get(key)
        return dt_util.parse_datetime(raw) if raw else None

    @property
    def installed_at_dt(self) -> datetime:
        return dt_util.parse_datetime(self.installed_at) or dt_util.utcnow()

    @property
    def combined_chlorine(self) -> float | None:
        """Chloramine, by subtraction — or None when the maths would lie.

        Total minus free only means something when both figures describe the
        same water: a total from today minus a free from last week is noise
        with a unit. The two have to have been measured within the same test
        session, give or take an afternoon.
        """
        total = self.values.get(KEY_TOTAL_CHLORINE)
        free = self.values.get(KEY_FREE_CHLORINE)
        if not isinstance(total, (int, float)) or not isinstance(free, (int, float)):
            return None
        total_at = dt_util.parse_datetime(self.values_at.get(KEY_TOTAL_CHLORINE) or "")
        free_at = dt_util.parse_datetime(self.values_at.get(KEY_FREE_CHLORINE) or "")
        if total_at is None or free_at is None:
            return None
        if abs(total_at - free_at) > timedelta(hours=COMBINED_CHLORINE_WINDOW_HOURS):
            return None
        # A strip reading total below free is measurement noise, not
        # negative chloramine.
        return round(max(0.0, float(total) - float(free)), 2)

    @callback
    def async_set_value(self, key: str, value: Any) -> None:
        """Set a declarative value (used by number/select entities in the UI)."""
        self.values[key] = value
        self.values_at[key] = dt_util.utcnow().isoformat()
        self.async_update_listeners()
        self.async_save()

    @callback
    def async_set_maintenance_mode(
        self,
        on: bool,
        person: str | None = None,
        until: str | None = None,
        plan: dict[str, str] | None = None,
    ) -> bool:
        """Raise or drop the maintenance flag; True when anything changed.

        ``person`` is whoever flipped it on the page — left empty when it came
        from Home Assistant itself, where the logbook already says who.

        Turning it on while it is already on is a re-arm: the window and the
        plan are replaced, but ``maintenance_mode_at`` stays put. "Since" has
        to keep meaning since when somebody has been working, not since the
        last time they changed their mind about the heat pump.
        """
        before = (
            self.maintenance_mode,
            self.maintenance_mode_at,
            self.maintenance_mode_by,
            self.maintenance_mode_until,
            self.maintenance_mode_plan,
        )
        if self.maintenance_mode != on:
            self.maintenance_mode = on
            self.maintenance_mode_at = dt_util.utcnow().isoformat()
            self.maintenance_mode_by = person or None
        elif on and person:
            self.maintenance_mode_by = person
        if on:
            self.maintenance_mode_until = until
            self.maintenance_mode_plan = dict(plan or {})
        else:
            # The window is over; what was asked for outlives it. Whoever
            # reacts to the flag dropping may still need to know what was
            # done, so the plan stays until the next visit replaces it.
            self.maintenance_mode_until = None
        if before == (
            self.maintenance_mode,
            self.maintenance_mode_at,
            self.maintenance_mode_by,
            self.maintenance_mode_until,
            self.maintenance_mode_plan,
        ):
            return False
        self.async_update_listeners()
        self.async_save()
        return True

    @callback
    def async_apply(self, result: ProcessResult) -> None:
        """Apply an accepted maintenance record and notify all consumers."""
        self.values.update(result.values)
        # Back-dated records really are older; the timestamp says so.
        logged_at = result.record["logged_at"]
        for key in result.values:
            self.values_at[key] = logged_at
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
    def async_delete_record(self, record_id: str | None = None) -> bool:
        """Delete a record (the most recent one when no id is given).

        Timestamps are rebuilt by replaying the remaining records, so a
        mistaken "filter washed" entry no longer counts. Declared values
        are left untouched — they are directly editable as entities.
        """
        from .processor import record_timestamps

        if not self.records:
            return False
        if record_id is None:
            self.records.pop()
        else:
            index = next(
                (i for i, record in enumerate(self.records) if record.get("id") == record_id),
                None,
            )
            if index is None:
                return False
            self.records.pop(index)

        self.timestamps = {}
        for record in sorted(self.records, key=lambda item: item.get("logged_at") or ""):
            self.timestamps.update(
                record_timestamps(
                    record.get("categories", []),
                    record.get("data", {}),
                    record["logged_at"],
                )
            )
        self.last_record = self.records[-1] if self.records else None
        self.async_update_listeners()
        self.async_save()
        return True

    @callback
    def async_add_note(
        self, person: str, text: str, created_at: str | None = None
    ) -> dict[str, Any]:
        """Append a note to the page-only diary (no entity involved)."""
        note = {
            "id": ulid_util.ulid_now(),
            "person": person,
            "created_at": created_at or dt_util.utcnow().isoformat(),
            "text": text,
        }
        self.notes.append(note)
        del self.notes[:-MAX_NOTES]
        self.async_save()
        return note

    @callback
    def async_update_listeners(self) -> None:
        async_dispatcher_send(self.hass, signal_updated(self.entry_id))
