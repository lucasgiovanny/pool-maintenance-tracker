"""Sensor entities: last-done timestamps, last record summary, access URL."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.network import NoURLAvailableError, get_url
from homeassistant.util import dt as dt_util

from .const import (
    CONF_TOKEN,
    RECENT_RECORDS_ATTR_COUNT,
    TS_CLEANING,
    URL_PAGE,
)
from .entity import PoolBaseEntity
from .modules import enabled_timestamp_keys, timestamp_sensor_key

if TYPE_CHECKING:
    from . import PoolConfigEntry

ICONS = {
    "last_water_test": "mdi:test-tube",
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
    entities.append(PoolAccessUrlSensor(entry))
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


class PoolLastRecordSensor(PoolBaseEntity, SensorEntity):
    """Summary of the last accepted record."""

    _attr_icon = "mdi:clipboard-text-clock"

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


class PoolAccessUrlSensor(PoolBaseEntity, SensorEntity):
    """Full public URL of the maintenance page (for QR/NFC writing)."""

    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:qrcode-scan"

    def __init__(self, entry: PoolConfigEntry) -> None:
        super().__init__(entry, "access_url")

    @property
    def native_value(self) -> str | None:
        path = URL_PAGE.format(token=self.entry.data[CONF_TOKEN])
        try:
            base = get_url(self.hass, prefer_external=True)
        except NoURLAvailableError:
            return None
        return f"{base}{path}"
