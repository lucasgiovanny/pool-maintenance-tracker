"""Binary sensors flagging overdue maintenance tasks."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

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
        days = int(self.entry.options.get(self.spec.conf_key, self.spec.default_days))
        reminders = self.entry.runtime_data.reminders
        return reminders.is_overdue(self.spec.timestamp_key, days, dt_util.utcnow())

    @property
    def extra_state_attributes(self) -> dict[str, int]:
        return {
            "interval_days": int(self.entry.options.get(self.spec.conf_key, self.spec.default_days))
        }
