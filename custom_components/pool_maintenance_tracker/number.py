"""Number entities for declared pool values."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.number import NumberEntity, NumberMode
from homeassistant.const import (
    CONCENTRATION_PARTS_PER_MILLION,
    UnitOfMass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    KEY_CHLORINATOR_OUTPUT,
    KEY_FREE_CHLORINE,
    KEY_PH,
    KEY_SALT_ADDED,
    KEY_SALT_LEVEL,
    NUMBER_RANGES,
)
from .entity import PoolBaseEntity
from .modules import enabled_value_keys

if TYPE_CHECKING:
    from . import PoolConfigEntry

UNITS = {
    KEY_PH: None,
    KEY_FREE_CHLORINE: CONCENTRATION_PARTS_PER_MILLION,
    KEY_SALT_LEVEL: "g/L",
    KEY_SALT_ADDED: UnitOfMass.KILOGRAMS,
    KEY_CHLORINATOR_OUTPUT: "g/h",
}

ICONS = {
    KEY_PH: "mdi:ph",
    KEY_FREE_CHLORINE: "mdi:test-tube",
    KEY_SALT_LEVEL: "mdi:shaker-outline",
    KEY_SALT_ADDED: "mdi:shaker",
    KEY_CHLORINATOR_OUTPUT: "mdi:lightning-bolt-outline",
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
        self._attr_icon = ICONS[key]

    @property
    def native_value(self) -> float | None:
        return self.tracker.values.get(self.key)

    async def async_set_native_value(self, value: float) -> None:
        self.tracker.async_set_value(self.key, round(value, 2))
