"""The optional maintenance-mode flag, as a switch.

The one entity in this integration that exists purely to be read by
somebody else's automation: nothing here reacts to it. Turning it on says
"a person is working on this pool right now" — stopping the pump, muting a
water alarm or skipping tonight's schedule is the automation's decision,
not ours.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import (
    CONF_MAINTENANCE_MODE,
    DEFAULT_MAINTENANCE_MODE,
    KEY_MAINTENANCE_MODE,
)
from .entity import PoolBaseEntity

if TYPE_CHECKING:
    from . import PoolConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: PoolConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    if entry.options.get(CONF_MAINTENANCE_MODE, DEFAULT_MAINTENANCE_MODE):
        async_add_entities([PoolMaintenanceModeSwitch(entry)])


class PoolMaintenanceModeSwitch(PoolBaseEntity, SwitchEntity):
    """On while the pool is being worked on."""

    _attr_icon = "mdi:account-wrench"

    def __init__(self, entry: PoolConfigEntry) -> None:
        super().__init__(entry, KEY_MAINTENANCE_MODE)

    @property
    def is_on(self) -> bool:
        return self.tracker.maintenance_mode

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Since when, and who said so — the page can name the technician."""
        return {
            "since": self.tracker.maintenance_mode_at,
            "set_by": self.tracker.maintenance_mode_by,
        }

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.tracker.async_set_maintenance_mode(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.tracker.async_set_maintenance_mode(False)
