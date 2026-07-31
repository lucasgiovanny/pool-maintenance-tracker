"""Doing what the technician asked, and undoing it when the window closes.

This is the one place in the integration that commands equipment. Two rules
keep that honest. It only ever touches entities the owner assigned to a role
of this pool — the page sends a role, never an entity id, so the reach of a
maintenance plan is exactly the equipment list in the options. And every
change goes through the service layer, so it shows up in the logbook like any
other change, attributable to one maintenance session.

The window itself never commands anything: running out only drops the flag,
and dropping the flag is what puts the equipment back.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any

from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_CLOSE_COVER,
    SERVICE_OPEN_COVER,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
    STATE_UNKNOWN,
)
from homeassistant.core import Context, HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.util import dt as dt_util

from .const import (
    CONF_MAINTENANCE_MODE,
    DEFAULT_MAINTENANCE_MODE,
    EQUIPMENT_ROLES,
    MAINTENANCE_DOMAINS,
    MAINTENANCE_MAX_MINUTES,
    MAINTENANCE_MIN_MINUTES,
    MAINTENANCE_ROLES,
    maintenance_values,
    signal_updated,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .tracker import PoolTracker

_LOGGER = logging.getLogger(__name__)

# Cover states that mean "it was closed"; the rest count as open.
CLOSED_STATES = ("closed", "closing")
SERVICE_SET_HVAC_MODE = "set_hvac_mode"
SERVICE_SET_OPERATION_MODE = "set_operation_mode"


class PlanError(ValueError):
    """The window or the equipment plan could not be read."""


@callback
def is_enabled(entry: ConfigEntry) -> bool:
    """Whether this pool keeps the maintenance flag at all."""
    return bool(entry.options.get(CONF_MAINTENANCE_MODE, DEFAULT_MAINTENANCE_MODE))


def parse_minutes(raw: Any) -> str | None:
    """Turn a requested duration into the moment the window closes.

    Absent, null or zero means no limit: some jobs take as long as they take.
    """
    if raw is None:
        return None
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        raise PlanError("minutes must be a number")
    minutes = int(raw)
    if minutes == 0:
        return None
    if not MAINTENANCE_MIN_MINUTES <= minutes <= MAINTENANCE_MAX_MINUTES:
        raise PlanError(
            f"minutes must be between {MAINTENANCE_MIN_MINUTES} and {MAINTENANCE_MAX_MINUTES}"
        )
    return (dt_util.utcnow() + timedelta(minutes=minutes)).isoformat()


@callback
def role_target(hass: HomeAssistant, entry: ConfigEntry, role: str) -> tuple[str, str] | None:
    """The entity and domain behind a role, when it is one we can command."""
    if role not in MAINTENANCE_ROLES:
        return None
    entity_id = entry.options.get(EQUIPMENT_ROLES[role])
    if not entity_id:
        return None
    domain = entity_id.partition(".")[0]
    if domain not in MAINTENANCE_DOMAINS:
        return None
    return entity_id, domain


@callback
def clean_plan(
    hass: HomeAssistant, entry: ConfigEntry, raw: Any
) -> tuple[dict[str, str], list[str]]:
    """Keep the roles this pool can actually command, in their own words.

    Anything else is dropped and named in the returned list, the way the log
    endpoint reports the values it could not use.
    """
    if raw is None:
        return {}, []
    if not isinstance(raw, dict):
        raise PlanError("equipment must be an object")
    plan: dict[str, str] = {}
    ignored: list[str] = []
    for role, value in raw.items():
        target = role_target(hass, entry, str(role))
        if target is None or value not in maintenance_values(target[1]):
            ignored.append(f"equipment.{role}")
            continue
        plan[str(role)] = value
    return plan, ignored


def _apply_call(domain: str, value: str) -> str:
    """The service that puts a role where the technician asked for it."""
    if domain == "cover":
        return SERVICE_OPEN_COVER if value == "open" else SERVICE_CLOSE_COVER
    return SERVICE_TURN_ON if value == "on" else SERVICE_TURN_OFF


def _restore_call(domain: str, before: str) -> tuple[str, dict[str, Any]]:
    """The service that puts a role back where it was, and its extra data."""
    if domain == "cover":
        return (SERVICE_CLOSE_COVER if before in CLOSED_STATES else SERVICE_OPEN_COVER), {}
    if before == STATE_OFF:
        return SERVICE_TURN_OFF, {}
    # A thermostat was not merely "on": it was heating, or on eco. Naming the
    # mode again beats turning it on and letting it guess.
    if domain == "climate" and before != STATE_ON:
        return SERVICE_SET_HVAC_MODE, {"hvac_mode": before}
    if domain == "water_heater" and before != STATE_ON:
        return SERVICE_SET_OPERATION_MODE, {"operation_mode": before}
    return SERVICE_TURN_ON, {}


async def _async_command(
    hass: HomeAssistant,
    entity_id: str,
    domain: str,
    service: str,
    data: dict[str, Any],
    context: Context,
) -> str | None:
    """Make one call; return the reason it could not be made, or None."""
    if not hass.services.has_service(domain, service):
        return "unsupported"
    try:
        await hass.services.async_call(
            domain,
            service,
            {ATTR_ENTITY_ID: entity_id, **data},
            blocking=True,
            context=context,
        )
    except HomeAssistantError as err:
        _LOGGER.warning("Maintenance mode could not call %s on %s: %s", service, entity_id, err)
        return "failed"
    return None


async def async_apply(
    hass: HomeAssistant, entry: ConfigEntry, plan: dict[str, str]
) -> dict[str, dict[str, str]]:
    """Put the equipment where the technician asked, and say how it went.

    Every role that moves is photographed first, and only the first time: a
    re-arm halfway through the job must not record our own handiwork as the
    state to come back to. One failure is reported, not raised — the rest of
    the plan still deserves to happen.
    """
    tracker: PoolTracker = entry.runtime_data.tracker
    applied: dict[str, str] = {}
    failed: dict[str, str] = {}
    context = Context()
    for role, value in plan.items():
        target = role_target(hass, entry, role)
        if target is None:
            failed[role] = "not_configured"
            continue
        entity_id, domain = target
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            failed[role] = "unavailable"
            continue
        reason = await _async_command(
            hass, entity_id, domain, _apply_call(domain, value), {}, context
        )
        if reason:
            failed[role] = reason
            continue
        tracker.maintenance_mode_restore.setdefault(role, state.state)
        applied[role] = value
    if applied:
        tracker.async_save()
    return {"applied": applied, "failed": failed}


async def async_restore(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Put back what the maintenance changed, politely.

    The photograph is taken away before anything else happens, so whoever
    gets here first does the work and a second caller is a no-op. A role is
    only put back while our own change is still standing: if somebody moved
    it since, theirs is the newer word and it stays.
    """
    tracker: PoolTracker = entry.runtime_data.tracker
    snapshot = tracker.maintenance_mode_restore
    if not snapshot:
        return {}
    tracker.maintenance_mode_restore = {}
    tracker.async_save()

    restored: dict[str, str] = {}
    context = Context()
    for role, before in snapshot.items():
        target = role_target(hass, entry, role)
        if target is None:
            continue
        entity_id, domain = target
        state = hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNAVAILABLE, STATE_UNKNOWN):
            continue
        # Already back where it was — by our hand or somebody else's.
        if state.state == before:
            continue
        service, data = _restore_call(domain, before)
        if not await _async_command(hass, entity_id, domain, service, data, context):
            restored[role] = before
    if restored:
        _LOGGER.debug("Maintenance mode restored %s for %s", restored, entry.title)
    return restored


class MaintenanceSession:
    """Closes the maintenance window, and puts the equipment back after it.

    Both edges are watched here rather than at the doors people come in
    through, because the flag can be dropped from four of them — the window
    running out, the page, the switch in Home Assistant, the action — and
    only one of those has a request waiting for an answer.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, tracker: PoolTracker) -> None:
        self.hass = hass
        self.entry = entry
        self.tracker = tracker
        self._unsub_signal = None
        self._unsub_timer = None
        self._armed: str | None = None
        self._was_on = tracker.maintenance_mode

    @callback
    def async_start(self) -> None:
        """Follow the tracker, and catch up with whatever it already says.

        Catching up is what handles a restart: a window that ran out while
        Home Assistant was down closes here, at startup, and the equipment
        goes back with it.
        """
        self._unsub_signal = async_dispatcher_connect(
            self.hass, signal_updated(self.entry.entry_id), self._async_sync
        )
        self._async_sync()

    @callback
    def async_stop(self) -> None:
        if self._unsub_signal is not None:
            self._unsub_signal()
            self._unsub_signal = None
        self._async_disarm()

    @callback
    def _async_disarm(self) -> None:
        if self._unsub_timer is not None:
            self._unsub_timer()
            self._unsub_timer = None
        self._armed = None

    @callback
    def _async_sync(self) -> None:
        """Match the armed timer to the window the tracker is holding.

        Called on every tracker change, readings and records included, so it
        stays a string comparison and a bool.
        """
        on = self.tracker.maintenance_mode
        if self._was_on and not on:
            self._was_on = False
            self._async_disarm()
            self.entry.async_create_task(self.hass, async_restore(self.hass, self.entry))
            return
        self._was_on = on

        until = self.tracker.maintenance_mode_until if on else None
        target = dt_util.parse_datetime(until) if until else None
        if target is None:
            self._async_disarm()
            return
        if target <= dt_util.utcnow():
            # Dropping the flag re-enters here through the dispatcher, which
            # is where the restore is started; nothing left to do afterwards.
            self._async_disarm()
            self.tracker.async_set_maintenance_mode(False)
            return
        if self._armed == until:
            return
        self._async_disarm()
        self._armed = until
        self._unsub_timer = async_track_point_in_utc_time(self.hass, self._async_expire, target)

    @callback
    def _async_expire(self, now: datetime) -> None:
        """The window ran out. Clear the handle before it fires again."""
        self._unsub_timer = None
        self._armed = None
        self.tracker.async_set_maintenance_mode(False)
