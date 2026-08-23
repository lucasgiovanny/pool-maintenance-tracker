"""Number entities for declared pool values."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberMode,
)
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    UnitOfMass,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    KEY_CALCIUM_HARDNESS,
    KEY_CHLORINATOR_OUTPUT,
    KEY_CYANURIC_ACID,
    KEY_FREE_CHLORINE,
    KEY_PH,
    KEY_SALT_ADDED,
    KEY_SALT_LEVEL,
    KEY_TOTAL_ALKALINITY,
    KEY_TOTAL_CHLORINE,
    KEY_WATER_TEMPERATURE,
    NUMBER_RANGES,
)
from .entity import PoolBaseEntity
from .modules import enabled_value_keys

# Everything is pushed from the tracker; nothing here polls.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from . import PoolConfigEntry

UNITS = {
    KEY_PH: None,
    KEY_FREE_CHLORINE: CONCENTRATION_PARTS_PER_MILLION,
    KEY_TOTAL_CHLORINE: CONCENTRATION_PARTS_PER_MILLION,
    KEY_TOTAL_ALKALINITY: CONCENTRATION_PARTS_PER_MILLION,
    KEY_CYANURIC_ACID: CONCENTRATION_PARTS_PER_MILLION,
    KEY_CALCIUM_HARDNESS: CONCENTRATION_PARTS_PER_MILLION,
    KEY_WATER_TEMPERATURE: UnitOfTemperature.CELSIUS,
    KEY_SALT_LEVEL: "g/L",
    KEY_SALT_ADDED: UnitOfMass.KILOGRAMS,
    KEY_CHLORINATOR_OUTPUT: "g/h",
}


DEVICE_CLASSES = {
    KEY_WATER_TEMPERATURE: NumberDeviceClass.TEMPERATURE,
    KEY_PH: NumberDeviceClass.PH,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    keys = enabled_value_keys(entry.options)
    async_add_entities(PoolNumber(entry, key) for key in NUMBER_RANGES if key in keys)


class PoolNumber(PoolBaseEntity, NumberEntity):
    """A manually declared numeric reading/setting."""

    _attr_mode = NumberMode.BOX

    def __init__(self, entry: PoolConfigEntry, key: str) -> None:
        super().__init__(entry, key)
        minimum, maximum, step = NUMBER_RANGES[key]
        self._attr_native_min_value = minimum
        self._attr_native_max_value = maximum
        self._attr_native_step = step
        self._attr_native_unit_of_measurement = UNITS[key]
        if key in DEVICE_CLASSES:
            self._attr_device_class = DEVICE_CLASSES[key]

    @property
    def native_value(self) -> float | None:
        return self.tracker.values.get(self.key)

    async def async_set_native_value(self, value: float) -> None:
        self.tracker.async_set_value(self.key, round(value, 2))
