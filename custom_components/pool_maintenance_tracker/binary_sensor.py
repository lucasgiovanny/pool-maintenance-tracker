"""Binary sensors flagging overdue maintenance tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import filter_pressure
from .const import TS_FILTER_WASH
from .entity import PoolBaseEntity
from .modules import ReminderSpec, enabled_reminders

if TYPE_CHECKING:
    from . import PoolConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities(
        PoolDueBinarySensor(entry, spec) for spec in enabled_reminders(entry.options)
    )


class PoolDueBinarySensor(PoolBaseEntity, BinarySensorEntity):
    """On when a periodic maintenance task is overdue."""

    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, entry: PoolConfigEntry, spec: ReminderSpec) -> None:
        super().__init__(entry, f"{spec.timestamp_key}_due")
        self.spec = spec

    @property
    def is_on(self) -> bool:
        runtime = self.entry.runtime_data
        if self.spec.timestamp_key == TS_FILTER_WASH:
            by_pressure = filter_pressure.is_due(self.entry, runtime.tracker)
            if by_pressure is not None:
                return by_pressure
        days = int(self.entry.options.get(self.spec.conf_key, self.spec.default_days))
        return runtime.reminders.is_overdue(self.spec.timestamp_key, days, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Say which rule decided, so an automation can tell them apart."""
        runtime = self.entry.runtime_data
        attributes: dict[str, Any] = {
            "interval_days": int(
                self.entry.options.get(self.spec.conf_key, self.spec.default_days)
            ),
            "criterion": "interval",
        }
        if self.spec.timestamp_key == TS_FILTER_WASH and filter_pressure.rules_the_alert(
            self.entry, runtime.tracker
        ):
            snapshot = filter_pressure.snapshot(self.hass, self.entry, runtime.tracker) or {}
            attributes.update(
                criterion="pressure",
                pressure=snapshot.get("value"),
                clean_pressure=snapshot.get("clean"),
                rise_percent=snapshot.get("rise_percent"),
                threshold_percent=snapshot.get("threshold_percent"),
            )
        return attributes
