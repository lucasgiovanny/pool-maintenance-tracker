"""Select entities for declared pool settings."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    ACID_TANK_LEVELS,
    CHLORINATOR_MODES,
    KEY_ACID_TANK_LEVEL,
    KEY_CHLORINATOR_MODE,
)
from .entity import PoolBaseEntity
from .modules import enabled_value_keys

# Everything is pushed from the tracker; nothing here polls.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from . import PoolConfigEntry

SELECT_OPTIONS = {
    KEY_CHLORINATOR_MODE: CHLORINATOR_MODES,
    KEY_ACID_TANK_LEVEL: ACID_TANK_LEVELS,
}


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    keys = enabled_value_keys(entry.options)
    async_add_entities(PoolSelect(entry, key) for key in SELECT_OPTIONS if key in keys)


class PoolSelect(PoolBaseEntity, SelectEntity):
    """A manually declared enumerated setting."""

    def __init__(self, entry: PoolConfigEntry, key: str) -> None:
        super().__init__(entry, key)
        self._attr_options = list(SELECT_OPTIONS[key])

    @property
    def current_option(self) -> str | None:
        return self.tracker.values.get(self.key)

    async def async_select_option(self, option: str) -> None:
        self.tracker.async_set_value(self.key, option)
