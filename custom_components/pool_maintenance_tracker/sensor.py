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
    KEY_PH,
    KEY_WATER_TEMPERATURE,
    MEASUREMENT_KEYS,
    RECENT_RECORDS_ATTR_COUNT,
    TS_CLEANING,
    measurement_sensor_key,
)
from .entity import PoolBaseEntity
from .modules import active_entity_keys, enabled_timestamp_keys, timestamp_sensor_key
from .number import ICONS as VALUE_ICONS
from .number import UNITS as VALUE_UNITS

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
    active = active_entity_keys(entry.options)
    if KEY_COMBINED_CHLORINE in active:
        entities.append(PoolCombinedChlorineSensor(entry))
    entities.extend(
        PoolMeasurementSensor(entry, key)
        for key in MEASUREMENT_KEYS
        if measurement_sensor_key(key) in active
    )
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


class PoolMeasurementSensor(PoolBaseEntity, SensorEntity):
    """The declared water measurement, as a sensor with statistics.

    The ``number`` entity is the pen — it exists to be written with. Numbers
    never feed Home Assistant's long-term statistics, so on its own the most
    important data in the integration would evaporate with the recorder
    purge. This mirror is the archive: same value, read-only, kept by HA
    for as long as HA keeps statistics — which is forever.
    """

    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, entry: PoolConfigEntry, value_key: str) -> None:
        super().__init__(entry, measurement_sensor_key(value_key))
        self.value_key = value_key
        self._attr_native_unit_of_measurement = VALUE_UNITS[value_key]
        self._attr_icon = VALUE_ICONS[value_key]
        if value_key == KEY_PH:
            self._attr_device_class = SensorDeviceClass.PH
        elif value_key == KEY_WATER_TEMPERATURE:
            self._attr_device_class = SensorDeviceClass.TEMPERATURE

    @property
    def native_value(self) -> float | None:
        value = self.tracker.values.get(self.value_key)
        return value if isinstance(value, (int, float)) else None


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
