"""Base entity for Pool Maintenance Tracker."""

from __future__ import annotations

from typing import TYPE_CHECKING

from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, signal_updated

if TYPE_CHECKING:
    from . import PoolConfigEntry
    from .tracker import PoolTracker


class PoolBaseEntity(Entity):
    """Thin view over the PoolTracker, refreshed via the dispatcher."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, entry: PoolConfigEntry, key: str) -> None:
        self.entry = entry
        self.tracker: PoolTracker = entry.runtime_data.tracker
        self.key = key
        self._attr_unique_id = f"{entry.entry_id}_{key}"
        self._attr_translation_key = key
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry.entry_id)},
            name=entry.data[CONF_NAME],
            manufacturer="Pool Maintenance Tracker",
        )

    async def async_added_to_hass(self) -> None:
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_updated(self.entry.entry_id), self._handle_update
            )
        )

    @callback
    def _handle_update(self) -> None:
        self.async_write_ha_state()
