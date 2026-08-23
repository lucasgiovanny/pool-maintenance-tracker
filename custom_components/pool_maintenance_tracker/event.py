"""Event entity fired for every accepted maintenance record."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.event import EventEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import signal_record
from .entity import PoolBaseEntity

# Everything is pushed from the tracker; nothing here polls.
PARALLEL_UPDATES = 0

if TYPE_CHECKING:
    from . import PoolConfigEntry

EVENT_TYPE_LOGGED = "logged"


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([PoolRecordEventEntity(entry)])


class PoolRecordEventEntity(PoolBaseEntity, EventEntity):
    """Fires a ``logged`` event with the full record payload."""

    _attr_event_types = [EVENT_TYPE_LOGGED]  # noqa: RUF012

    def __init__(self, entry: PoolConfigEntry) -> None:
        super().__init__(entry, "maintenance_logged")

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, signal_record(self.entry.entry_id), self._handle_record
            )
        )

    @callback
    def _handle_record(self, record: dict[str, Any]) -> None:
        self._trigger_event(EVENT_TYPE_LOGGED, record)
        self.async_write_ha_state()
