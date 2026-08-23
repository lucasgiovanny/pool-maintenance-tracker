"""Sensor entities: last-done timestamps, last record summary, access URL."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from .const import (
    KEY_COMBINED_CHLORINE,
    RECENT_RECORDS_ATTR_COUNT,
    TS_CLEANING,
)
from .entity import PoolBaseEntity
from .modules import active_entity_keys, enabled_timestamp_keys, timestamp_sensor_key

# Everything is pushed from the tracker; nothing here polls.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from . import PoolConfigEntry

ICONS = {
    "last_water_test": "mdi:test-tube",
    "last_chemistry_test": "mdi:beaker-check",
    "last_salt_added": "mdi:shaker",
    "last_filter_wash": "mdi:air-filter",
    "last_cell_clean": "mdi:battery-heart-variant",
    "last_probe_calibration": "mdi:tune-vertical",
    "last_acid_refill": "mdi:water-plus",
    "last_cleaning": "mdi:broom",
    "last_maintenance": "mdi:pool",
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    entities: list[SensorEntity] = [
        PoolTimestampSensor(entry, ts_key) for ts_key in enabled_timestamp_keys(entry.options)
    ]
    entities.append(PoolLastRecordSensor(entry))
    if KEY_COMBINED_CHLORINE in active_entity_keys(entry.options):
        entities.append(PoolCombinedChlorineSensor(entry))
    async_add_entities(entities)


class PoolTimestampSensor(PoolBaseEntity, SensorEntity):
    """When a maintenance task was last done."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, entry: PoolConfigEntry, timestamp_key: str) -> None:
        super().__init__(entry, timestamp_sensor_key(timestamp_key))
        self.timestamp_key = timestamp_key
        self._attr_icon = ICONS.get(self.key)

    @property
    def native_value(self) -> datetime | None:
        return self.tracker.get_timestamp(self.timestamp_key)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.timestamp_key != TS_CLEANING:
            return None
        if types := self.tracker.values.get("cleaning_types"):
            return {"types": types}
        return None


class PoolCombinedChlorineSensor(PoolBaseEntity, SensorEntity):
    """Total minus free chlorine — the chloramine figure.

    Unknown rather than stale: when the two readings did not come from the
    same test session the subtraction is meaningless and the sensor says so.
    """

    _attr_icon = "mdi:flask-outline"
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: PoolConfigEntry) -> None:
        super().__init__(entry, KEY_COMBINED_CHLORINE)

    @property
    def native_value(self) -> float | None:
        return self.tracker.combined_chlorine


class PoolLastRecordSensor(PoolBaseEntity, SensorEntity):
    """Summary of the last accepted record."""

    _attr_icon = "mdi:clipboard-text-clock"
    # The tracker's own Store is the log; the recorder does not need a copy
    # of twenty records glued to every state change.
    _unrecorded_attributes = frozenset({"recent_records", "data"})

    def __init__(self, entry: PoolConfigEntry) -> None:
        super().__init__(entry, "last_record")

    @property
    def native_value(self) -> str | None:
        record = self.tracker.last_record
        if not record:
            return None
        logged_at = dt_util.parse_datetime(record["logged_at"])
        stamp = dt_util.as_local(logged_at).strftime("%d/%m %H:%M") if logged_at else "?"
        categories = ", ".join(record["categories"]) or "-"
        return f"{record['person']} · {stamp} · {categories}"[:255]

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        record = self.tracker.last_record or {}
        recent = [
            {
                "id": item.get("id"),
                "person": item.get("person"),
                "logged_at": item.get("logged_at"),
                "categories": item.get("categories", []),
            }
            for item in reversed(self.tracker.records[-RECENT_RECORDS_ATTR_COUNT:])
        ]
        return {
            "person": record.get("person"),
            "logged_at": record.get("logged_at"),
            "categories": record.get("categories", []),
            "data": record.get("data", {}),
            "recent_records": recent,
        }
