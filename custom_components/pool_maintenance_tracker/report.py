"""Building what every surface shows: the report, the history, the roles.

Pure data assembly — no aiohttp, no tokens, no rate limiting. The views in
``http.py``, the websocket API behind the card, and the kiosk all call in
here, which is what keeps the three surfaces telling the same story.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from time import monotonic
from typing import TYPE_CHECKING, Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import filter_pressure, maintenance
from .const import (
    CONF_FILTRATION_OFF_TIME_ENTITY,
    CONF_FILTRATION_ON_TIME_ENTITY,
    CONF_FILTRATION_SCHEDULE_ENTITY,
    CONF_FILTRATION_STATE_ENTITY,
    CONF_POOL_TYPE,
    CONF_POOL_VOLUME,
    CONF_REPORT_SENSORS,
    CONF_SALT_TARGET_MAX,
    CONF_SALT_TARGET_MIN,
    CONF_TEMPERATURE_SOURCE,
    DEFAULT_SALT_TARGET_MAX,
    DEFAULT_SALT_TARGET_MIN,
    EQUIPMENT_ROLES,
    IDEAL_CALCIUM_HARDNESS,
    IDEAL_CYANURIC,
    IDEAL_CYANURIC_SALT,
    IDEAL_FREE_CHLORINE,
    IDEAL_PH,
    IDEAL_TOTAL_ALKALINITY,
    KEY_CALCIUM_HARDNESS,
    KEY_CYANURIC_ACID,
    KEY_FREE_CHLORINE,
    KEY_PH,
    KEY_SALT_LEVEL,
    KEY_TOTAL_ALKALINITY,
    KEY_TOTAL_CHLORINE,
    LINKED_SOURCES,
    LINKED_VALUE_KEYS,
    MAINTENANCE_ROLES,
    ONOFF_DOMAINS,
    POOL_TYPE_SALT,
    RECENT_RECORDS_ATTR_COUNT,
    ROLE_FILTRATION_SCHEDULE,
    SCHEDULE_MODE_HELPER,
    SCHEDULE_MODE_TIMES,
    THERMOSTAT_DOMAINS,
    TS_ANY,
    UNAVAILABLE_STATES,
    equipment_on,
    maintenance_values,
    schedule_mode,
)
from .modules import enabled_reminders, enabled_timestamp_keys, enabled_value_keys

_LOGGER = logging.getLogger(__name__)

if TYPE_CHECKING:
    from .tracker import PoolTracker


@callback
def _maintenance_mode(entry: ConfigEntry) -> dict[str, Any]:
    """The maintenance flag as every surface shows it.

    ``enabled`` is the option; ``on`` is the flag itself. A disabled feature
    still reports its flag so nothing looks half-configured, but no surface
    offers the toggle.
    """
    tracker = entry.runtime_data.tracker
    return {
        "enabled": maintenance.is_enabled(entry),
        "on": tracker.maintenance_mode,
        "since": tracker.maintenance_mode_at,
        "by": tracker.maintenance_mode_by,
        "until": tracker.maintenance_mode_until,
        "equipment": tracker.maintenance_mode_plan,
    }


@callback
def _maintenance_equipment(hass: HomeAssistant, entry: ConfigEntry) -> list[dict[str, Any]]:
    """What the maintenance sheet can ask for, and where it stands now.

    Deliberately not built from ``_role_entities``: that one costs a recorder
    query per role to work out when each state really began, and a sheet only
    needs to know what is on right now.
    """
    equipment: list[dict[str, Any]] = []
    for role in MAINTENANCE_ROLES:
        target = maintenance.role_target(hass, entry, role)
        if target is None:
            continue
        entity_id, domain = target
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            continue
        equipment.append(
            {
                "role": role,
                "entity_id": entity_id,
                "name": state.attributes.get("friendly_name") or entity_id,
                "state": state.state,
                "on": equipment_on(domain, state.state),
                "values": list(maintenance_values(domain)),
            }
        )
    return equipment


@callback
def _live_values(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, dict[str, Any]]:
    """Current values of the linked external sensors (smart probe etc.)."""
    live: dict[str, dict[str, Any]] = {}
    for key, conf_key in LINKED_SOURCES.items():
        entity_id = entry.options.get(conf_key)
        if not entity_id or (state := hass.states.get(entity_id)) is None:
            continue
        try:
            value = float(state.state)
        except ValueError:
            continue
        live[key] = {
            "entity_id": entity_id,
            "value": round(value, 2),
            "unit": state.attributes.get("unit_of_measurement") or "",
            "at": state.last_updated.isoformat(),
        }
    return live


def _state_began(rows: list[tuple[str, Any]], current: str) -> Any | None:
    """When the current state actually began, ignoring unavailable gaps.

    A restart records unavailable -> <state>, which would make everything
    look like it "changed just now". Walk backwards through the recorded
    rows (ascending order), skipping unavailable/unknown, until a state
    different from the current one appears.
    """
    began = None
    for state, changed in reversed(rows):
        if state in ("unavailable", "unknown"):
            continue
        if state != current:
            break
        began = changed
    return began


async def _true_last_changed(
    hass: HomeAssistant, entity_id: str, current_state: str, fallback: str
) -> str:
    """When the entity's current state really began — survives HA restarts."""
    if not _recorder_ready(hass):
        return fallback
    from functools import partial

    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import get_last_state_changes

    try:
        states = await get_instance(hass).async_add_executor_job(
            partial(get_last_state_changes, hass, 25, entity_id)
        )
    except Exception:
        return fallback
    rows = sorted(
        ((row.state, row.last_changed) for row in states.get(entity_id) or []),
        key=lambda item: item[1],
    )
    began = _state_began(rows, current_state)
    return began.isoformat() if began else fallback


WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


async def _schedule_week(hass: HomeAssistant, entity_id: str) -> list[list[list[str]]] | None:
    """Weekly on-blocks of a UI-created schedule helper, read from HA storage.

    Returns 7 lists (Monday..Sunday) of [from, to] HH:MM pairs, or None when
    the schedule is not in storage (e.g. YAML-defined).
    """
    registry = er.async_get(hass)
    reg_entry = registry.async_get(entity_id)
    if reg_entry is None or reg_entry.platform != "schedule":
        return None

    from homeassistant.helpers.storage import Store

    data = await Store(hass, 1, "schedule").async_load()
    if not data:
        return None
    item = next(
        (it for it in data.get("items", []) if it.get("id") == reg_entry.unique_id),
        None,
    )
    if item is None:
        return None
    week = []
    for day in WEEKDAYS:
        blocks = []
        for block in item.get(day) or []:
            start = str(block.get("from", ""))[:5]
            end = str(block.get("to", ""))[:5]
            if start and end:
                # A block running to midnight is stored as "00:00" — as an
                # end time that means 24:00, not before the block starts.
                if end <= start:
                    end = "24:00"
                blocks.append([start, end])
        week.append(blocks)
    return week


def _minutes_of(text: str) -> int:
    hours, minutes = (int(part) for part in text.split(":")[:2])
    return hours * 60 + minutes


@callback
def _schedule_next_change(week: list[list[list[str]]], now: datetime) -> datetime | None:
    """When the schedule really flips next, merging blocks that touch.

    A schedule "on 22:00-24:00 Monday, 00:00-01:00 Tuesday" is one run that
    ends at 01:00 — but the raw block edges (and the entity's next_event)
    say it turns off at midnight, which is false: it never goes off.
    Expanding a week ahead into absolute intervals and merging the touching
    ones yields the boundary that actually changes the state.
    """
    local = dt_util.as_local(now)
    day_start = local.replace(hour=0, minute=0, second=0, microsecond=0)
    intervals: list[list[datetime]] = []
    for offset in range(9):  # a week ahead covers every repeating pattern
        day = day_start + timedelta(days=offset)
        for start, end in week[day.weekday() % 7]:
            begin = day + timedelta(minutes=_minutes_of(start))
            finish = day + timedelta(minutes=_minutes_of(end))
            if intervals and intervals[-1][1] == begin:
                intervals[-1][1] = finish  # touching blocks are one run
            else:
                intervals.append([begin, finish])
    for begin, finish in intervals:
        if finish <= local:
            continue
        return begin if begin > local else finish
    return None


def _time_of(hass: HomeAssistant, entity_id: str) -> str | None:
    """The wall-clock "HH:MM" behind whatever entity holds a time.

    A `time` entity says "08:00:00", an `input_datetime` may carry a date in
    front of it, and a controller's sensor says whatever it likes — an ISO
    timestamp, or just "8:00". All three mean one hour of one day.
    """
    state = hass.states.get(entity_id)
    if state is None or state.state in UNAVAILABLE_STATES:
        return None
    # input_datetime spells the parts out, which beats parsing its state.
    hour, minute = state.attributes.get("hour"), state.attributes.get("minute")
    if isinstance(hour, int) and isinstance(minute, int):
        return f"{hour:02d}:{minute:02d}"
    raw = state.state.strip()
    if moment := dt_util.parse_datetime(raw):
        # A timestamp sensor speaks UTC; the schedule is read off a wall clock.
        local = dt_util.as_local(moment) if moment.tzinfo else moment
        return f"{local.hour:02d}:{local.minute:02d}"
    parts = raw.split(":")
    try:
        hour, minute = int(parts[0]), int(parts[1]) if len(parts) > 1 else 0
    except (IndexError, ValueError):
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _times_week(on_time: str, off_time: str) -> list[list[list[str]]] | None:
    """One on/off pair as the weekly grid a schedule helper would produce.

    Two times describe the same day seven times over. A pair that ends
    before it starts runs through midnight, which the grid says with two
    blocks that touch at it — exactly how the helper stores such a night,
    so that everything reading the grid merges them back into one run.
    """
    if on_time == off_time:
        return None
    if off_time > on_time:
        day = [[on_time, off_time]]
    else:
        day = [["00:00", off_time]] if off_time > "00:00" else []
        day.append([on_time, "24:00"])
    return [[list(block) for block in day] for _ in WEEKDAYS]


def _in_block(week: list[list[list[str]]], now: datetime) -> bool:
    """Whether the grid has the filtration running at this local moment."""
    minutes = now.hour * 60 + now.minute
    return any(
        _minutes_of(start) <= minutes < _minutes_of(end) for start, end in week[now.weekday() % 7]
    )


@callback
def _times_schedule_item(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any] | None:
    """The filtration schedule of a pool whose controller owns it.

    The two times give the week; the state entity gives the present. Without
    one we read the present off the grid ourselves — a clock and a schedule
    are enough to know whether the pump should be running.
    """
    on_entity = entry.options.get(CONF_FILTRATION_ON_TIME_ENTITY)
    off_entity = entry.options.get(CONF_FILTRATION_OFF_TIME_ENTITY)
    if not on_entity or not off_entity:
        return None
    on_time, off_time = _time_of(hass, on_entity), _time_of(hass, off_entity)
    if on_time is None or off_time is None:
        return None
    week = _times_week(on_time, off_time)
    if week is None:
        return None
    scheduled = _in_block(week, dt_util.now())

    state_entity = entry.options.get(CONF_FILTRATION_STATE_ENTITY)
    state = hass.states.get(state_entity) if state_entity else None
    running: bool | None = None
    if state is not None:
        running = equipment_on(state_entity.split(".")[0], state.state)
    if running is None:
        # No sensor, or one that is not talking: the grid still knows.
        running = scheduled
    # A sensor that disagrees with the grid is somebody having overridden the
    # cycle by hand, and nothing here can know when they will hand it back.
    # Saying so beats counting down to a change that will not happen.
    next_change = _schedule_next_change(week, dt_util.utcnow()) if running == scheduled else None

    return {
        # Whatever the page opens when the row is tapped: the thing that
        # reports the state if there is one, the start time otherwise.
        "entity_id": state_entity or on_entity,
        "name": (state.attributes.get("friendly_name") if state else None) or on_entity,
        "state": "on" if running else "off",
        "on": running,
        "action": None,
        "target": None,
        "target_unit": "",
        "unit": "",
        # A schedule is what this is, whichever entities spell it out.
        "domain": "schedule",
        "next_change": next_change.isoformat() if next_change else None,
        "week": week,
        "last_changed": state.last_changed.isoformat() if state else None,
        # The card redraws when a watched entity moves, and moving the hours
        # changes this tile as surely as the pump switching on does.
        "sources": [entity for entity in (on_entity, off_entity, state_entity) if entity],
    }


async def _entity_item(hass: HomeAssistant, entity_id: str) -> dict[str, Any] | None:
    """Normalized snapshot of an external entity for the dashboards."""
    state = hass.states.get(entity_id)
    if state is None or state.state in ("unknown", "unavailable"):
        return None
    domain = entity_id.split(".")[0]
    next_change = None
    week = None
    if domain == "schedule":
        week = await _schedule_week(hass, entity_id)
        # Computed from the grid, because the entity's own next_event
        # reports a phantom off at midnight between touching blocks.
        if week is not None and (computed := _schedule_next_change(week, dt_util.utcnow())):
            next_change = computed.isoformat()
        if next_change is None and (next_event := state.attributes.get("next_event")):
            next_change = (
                next_event.isoformat() if hasattr(next_event, "isoformat") else str(next_event)
            )
    # A thermostat has more to say than on or off: whether it is working at
    # this moment, and the temperature it is working towards. Both are worth
    # more on a tile than the switch it does not get.
    action = None
    target = None
    target_unit = ""
    if domain in THERMOSTAT_DOMAINS:
        action = state.attributes.get("hvac_action")
        # In a heat/cool range there is no single target; the tile says
        # nothing rather than picking one of the two ends.
        raw_target = state.attributes.get("temperature")
        if isinstance(raw_target, (int, float)):
            target = raw_target
            target_unit = hass.config.units.temperature_unit
    return {
        "entity_id": entity_id,
        "name": state.attributes.get("friendly_name") or entity_id,
        "state": state.state,
        # Settled here so every surface agrees on what "running" means, rather
        # than each one guessing from the raw word the entity happens to use.
        "on": equipment_on(domain, state.state),
        "action": action,
        "target": target,
        "target_unit": target_unit,
        "unit": state.attributes.get("unit_of_measurement") or "",
        "domain": domain,
        "next_change": next_change,
        "week": week,
        "last_changed": await _true_last_changed(
            hass, entity_id, state.state, state.last_changed.isoformat()
        ),
    }


@callback
def _entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, str]:
    """Map our value/timestamp keys to the entity ids they materialized as."""
    registry = er.async_get(hass)
    prefix = f"{entry.entry_id}_"
    return {
        item.unique_id.removeprefix(prefix): item.entity_id
        for item in er.async_entries_for_config_entry(registry, entry.entry_id)
        if item.unique_id.startswith(prefix)
    }


async def _filtration_schedule_item(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any] | None:
    """The pool's filtration schedule, from a helper or from three entities."""
    mode = schedule_mode(entry.options)
    if mode == SCHEDULE_MODE_TIMES:
        return _times_schedule_item(hass, entry)
    if mode == SCHEDULE_MODE_HELPER and (
        entity_id := entry.options.get(CONF_FILTRATION_SCHEDULE_ENTITY)
    ):
        return await _entity_item(hass, entity_id)
    return None


async def _role_entities(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Entities the user explicitly assigned to a known role."""
    roles: dict[str, Any] = {}
    for role, conf_key in EQUIPMENT_ROLES.items():
        if role == ROLE_FILTRATION_SCHEDULE:
            # One role, two ways of holding it — settled in one place so the
            # rest of the report never has to ask which one this pool has.
            if item := await _filtration_schedule_item(hass, entry):
                roles[role] = item
            continue
        entity_id = entry.options.get(conf_key)
        if entity_id and (item := await _entity_item(hass, entity_id)):
            roles[role] = item
    return roles


@callback
def _ideal_ranges(entry: ConfigEntry) -> dict[str, dict[str, float]]:
    """Bands the readings are judged against on every surface."""
    # A cell's chlorine wants more stabilizer over it than a floater's
    cyanuric = (
        IDEAL_CYANURIC_SALT
        if entry.options.get(CONF_POOL_TYPE) == POOL_TYPE_SALT
        else IDEAL_CYANURIC
    )
    return {
        KEY_PH: {"min": IDEAL_PH[0], "max": IDEAL_PH[1]},
        KEY_FREE_CHLORINE: {
            "min": IDEAL_FREE_CHLORINE[0],
            "max": IDEAL_FREE_CHLORINE[1],
        },
        KEY_TOTAL_ALKALINITY: {
            "min": IDEAL_TOTAL_ALKALINITY[0],
            "max": IDEAL_TOTAL_ALKALINITY[1],
        },
        KEY_CYANURIC_ACID: {"min": cyanuric[0], "max": cyanuric[1]},
        KEY_CALCIUM_HARDNESS: {
            "min": IDEAL_CALCIUM_HARDNESS[0],
            "max": IDEAL_CALCIUM_HARDNESS[1],
        },
        KEY_SALT_LEVEL: {
            "min": float(entry.options.get(CONF_SALT_TARGET_MIN, DEFAULT_SALT_TARGET_MIN)),
            "max": float(entry.options.get(CONF_SALT_TARGET_MAX, DEFAULT_SALT_TARGET_MAX)),
        },
    }


def _today_scheduled_hours(week: list[list[list[str]]] | None) -> float | None:
    """Hours the filtration schedule runs today, from its weekly grid."""
    if not week:
        return None
    index = (dt_util.now().weekday()) % 7
    minutes = 0
    for start, end in week[index]:
        try:
            start_h, start_m = (int(part) for part in start.split(":")[:2])
            end_h, end_m = (int(part) for part in end.split(":")[:2])
        except ValueError:
            continue
        minutes += max(0, (end_h * 60 + end_m) - (start_h * 60 + start_m))
    return round(minutes / 60, 1)


@callback
def _current_readings(
    tracker: PoolTracker,
    values: dict[str, Any],
    live: dict[str, dict[str, Any]],
    entity_ids: dict[str, str],
) -> dict[str, dict[str, Any]]:
    """The freshest reading for each key, whoever took it.

    A linked probe and a manual entry both claim to be "the" temperature.
    Neither wins by rank — the most recent one wins, which is what somebody
    standing at the pool means by "the current value". Without a timestamp
    on the manual side we trust the probe, which at least knows when it
    last spoke.

    ``entity_id`` names the entity the winning value came from, so that a
    surface showing the number can also point at the thing that measured
    it, rather than at whichever of the two it happens to know about.
    """
    current: dict[str, dict[str, Any]] = {}
    for live_key, value_key in LINKED_VALUE_KEYS.items():
        probe = live.get(live_key)
        declared = values.get(value_key)
        declared_at = tracker.values_at.get(value_key)
        if probe is None and declared is None:
            continue
        use_probe = probe is not None and (
            declared is None or not declared_at or probe["at"] >= declared_at
        )
        if use_probe:
            current[value_key] = {
                "entity_id": probe.get("entity_id"),
                "value": probe["value"],
                "unit": probe["unit"],
                "source": "probe",
                "at": probe["at"],
                "other": declared,
            }
        else:
            current[value_key] = {
                "entity_id": entity_ids.get(value_key),
                "value": declared,
                "unit": "",
                "source": "manual",
                "at": declared_at,
                "other": probe["value"] if probe else None,
            }
    return current


async def _actual_hours_today(
    hass: HomeAssistant, entry: ConfigEntry, roles: dict[str, Any]
) -> float | None:
    """How long the filtration actually ran today, from the recorder.

    Schedules get overridden by hand, so what the pump really did is worth
    saying next to what it was asked to do. The answer is cached: the page
    and the kiosk both poll, and this costs a recorder query.
    """
    role = roles.get("pump") or roles.get("pool_system")
    if not role or not _recorder_ready(hass):
        return None
    cache = entry.runtime_data.cache
    now = monotonic()
    cached = cache.get(ACTUAL_HOURS_CACHE)
    if cached and now - cached[0] < ACTUAL_HOURS_TTL:
        return cached[1]

    start = dt_util.start_of_local_day()
    series = await _ontime_daily(hass, role["entity_id"], start, dt_util.utcnow())
    hours = series[-1]["v"] if series else None
    cache[ACTUAL_HOURS_CACHE] = (now, hours)
    return hours


async def _filtration_hours(
    hass: HomeAssistant, entry: ConfigEntry, roles: dict[str, Any]
) -> dict[str, Any] | None:
    """Today's filtration in hours: the plan, and what really happened.

    Both are facts about this pool — one read off its schedule, the other
    off the recorder. Nothing here judges them.
    """
    schedule = roles.get(ROLE_FILTRATION_SCHEDULE)
    hours = {
        "scheduled_hours": _today_scheduled_hours(schedule.get("week") if schedule else None),
        "actual_hours": await _actual_hours_today(hass, entry, roles),
    }
    return hours if any(value is not None for value in hours.values()) else None


ACTUAL_HOURS_CACHE = "actual_filtration_hours"

ACTUAL_HOURS_TTL = 300  # seconds — the page polls every 60, the kiosk every 30

REPORT_TASK_ORDER = (
    "water_test",
    "chemistry_test",
    "salt_added",
    "filter_wash",
    "cell_clean",
    "probe_calibration",
    "acid_refill",
    "cleaning",
)


async def _build_report(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """Snapshot of the pool state for the page's report tab."""
    runtime = entry.runtime_data
    tracker = runtime.tracker
    now = dt_util.utcnow()

    reminders_by_key = {spec.timestamp_key: spec for spec in enabled_reminders(entry.options)}
    tasks = []
    enabled_ts = enabled_timestamp_keys(entry.options)
    for ts_key in REPORT_TASK_ORDER:
        if ts_key not in enabled_ts:
            continue
        spec = reminders_by_key.get(ts_key)
        interval = int(entry.options.get(spec.conf_key, spec.default_days)) if spec else None
        next_due = (
            (runtime.reminders.overdue_since(ts_key) + timedelta(days=interval)).isoformat()
            if spec
            else None
        )
        tasks.append(
            {
                "key": ts_key,
                "last": tracker.timestamps.get(ts_key),
                "interval_days": interval,
                "next": next_due,
                "due": (runtime.reminders.is_overdue(ts_key, interval, now) if spec else False),
            }
        )

    allowed = enabled_value_keys(entry.options)
    values = {key: value for key, value in tracker.values.items() if key in allowed}

    records = [
        {
            "id": item.get("id"),
            "person": item.get("person"),
            "logged_at": item.get("logged_at"),
            "categories": item.get("categories", []),
            "data": item.get("data", {}),
            "snapshot": item.get("snapshot", {}),
        }
        for item in reversed(tracker.records[-RECENT_RECORDS_ATTR_COUNT:])
    ]

    roles = await _role_entities(hass, entry)
    role_ids = {item["entity_id"] for item in roles.values()}

    extra = []
    for entity_id in entry.options.get(CONF_REPORT_SENSORS, ()):
        # Entities with a named role already have their own place.
        if entity_id in role_ids:
            continue
        if item := await _entity_item(hass, entity_id):
            extra.append(item)

    live = _live_values(hass, entry)
    entity_ids = _entity_ids(hass, entry)
    current = _current_readings(tracker, values, live, entity_ids)

    return {
        "values": values,
        "current": current,
        # Derived, not declared — None when total and free chlorine were
        # not measured in the same test session.
        "combined_chlorine": tracker.combined_chlorine,
        "ranges": _ideal_ranges(entry),
        "volume": entry.options.get(CONF_POOL_VOLUME),
        "filtration": await _filtration_hours(hass, entry, roles),
        "filter_pressure": filter_pressure.snapshot(hass, entry, tracker),
        "maintenance_mode": _maintenance_mode(entry),
        # What a visit can ask for, so the card can offer the same sheet the
        # page does instead of only flipping the flag.
        "maintenance_equipment": _maintenance_equipment(hass, entry),
        "tasks": tasks,
        "last_maintenance": tracker.timestamps.get(TS_ANY),
        "records": records,
        "notes": list(reversed(tracker.notes)),
        "extra": extra,
        "roles": roles,
        "entity_ids": entity_ids,
    }


def _recorder_ready(hass: HomeAssistant) -> bool:
    return "recorder" in hass.config.components


async def _daily_means(hass: HomeAssistant, entity_id: str, start) -> list[dict[str, Any]]:
    """Daily mean series from HA long-term statistics (empty if none)."""
    if not _recorder_ready(hass):
        return []
    from functools import partial

    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import statistics_during_period

    stats = await get_instance(hass).async_add_executor_job(
        partial(
            statistics_during_period,
            hass,
            start,
            None,
            {entity_id},
            "day",
            None,
            {"mean"},
        )
    )
    points = []
    for row in stats.get(entity_id, []):
        mean = row.get("mean")
        if mean is None:
            continue
        raw_start = row.get("start")
        stamp = (
            dt_util.utc_from_timestamp(raw_start)
            if isinstance(raw_start, (int, float))
            else raw_start
        )
        points.append({"t": stamp.isoformat(), "v": round(float(mean), 2)})
    return points


async def _temperature_trend(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    """7-day daily means and the 24 h change of the linked temperature probe."""
    entity_id = entry.options.get(CONF_TEMPERATURE_SOURCE)
    trend: dict[str, Any] = {"series": [], "delta_24h": None}
    if not entity_id or not _recorder_ready(hass):
        return trend

    now = dt_util.utcnow()
    trend["series"] = await _daily_means(hass, entity_id, now - timedelta(days=7))

    from functools import partial

    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.statistics import statistics_during_period

    try:
        stats = await get_instance(hass).async_add_executor_job(
            partial(
                statistics_during_period,
                hass,
                now - timedelta(hours=26),
                None,
                {entity_id},
                "hour",
                None,
                {"mean"},
            )
        )
    except Exception:
        return trend
    means = [row["mean"] for row in stats.get(entity_id, []) if row.get("mean") is not None]
    if len(means) >= 2:
        trend["delta_24h"] = round(float(means[-1]) - float(means[0]), 1)
    return trend


def _ontime_buckets(domain: str, changes, start, end) -> list[dict[str, Any]]:
    """Hours running per local day from a list of (moment, state) changes.

    ``changes`` must be sorted and include the state at ``start``.
    Returns one point per local day between start and end (zeros included).
    """
    tz = dt_util.DEFAULT_TIME_ZONE
    seconds: dict[str, float] = {}
    day = dt_util.as_local(start).date()
    last_day = dt_util.as_local(end).date()
    while day <= last_day:
        seconds[day.isoformat()] = 0.0
        day = day + timedelta(days=1)

    intervals = [*changes, (end, None)]
    for index in range(len(intervals) - 1):
        moment, state = intervals[index]
        # A thermostat spends its working day saying "heat", never "on".
        if not equipment_on(domain, state or ""):
            continue
        block_start = max(moment, start)
        block_end = min(intervals[index + 1][0], end)
        cursor = block_start
        while cursor < block_end:
            local = dt_util.as_local(cursor)
            next_midnight = datetime.combine(
                local.date() + timedelta(days=1), datetime.min.time(), tz
            )
            segment_end = min(block_end, next_midnight)
            key = local.date().isoformat()
            if key in seconds:
                seconds[key] += (segment_end - cursor).total_seconds()
            cursor = segment_end

    return [{"t": key, "v": round(value / 3600, 1)} for key, value in seconds.items()]


async def _ontime_daily(hass: HomeAssistant, entity_id: str, start, end) -> list[dict[str, Any]]:
    """Hours-on per day computed from recorder history (limited by retention)."""
    if not _recorder_ready(hass):
        return []
    from functools import partial

    from homeassistant.components.recorder import get_instance
    from homeassistant.components.recorder.history import get_significant_states

    states = await get_instance(hass).async_add_executor_job(
        partial(get_significant_states, hass, start, end, [entity_id])
    )
    changes = [(state.last_changed, state.state) for state in states.get(entity_id, [])]
    if not changes:
        return []
    return _ontime_buckets(entity_id.split(".")[0], sorted(changes), start, end)


async def _build_history(hass: HomeAssistant, entry: ConfigEntry, days: int) -> dict[str, Any]:
    """Time series for the page's history tab."""
    tracker = entry.runtime_data.tracker
    end = dt_util.utcnow()
    start = end - timedelta(days=days)

    # Probe-linkable readings first, then the strip-only chemistry ones,
    # which chart the manual dots alone: (chart key, value key, conf key).
    specs: list[tuple[str, str, str | None]] = [
        (live_key, LINKED_VALUE_KEYS[live_key], conf_key)
        for live_key, conf_key in LINKED_SOURCES.items()
    ]
    allowed = enabled_value_keys(entry.options)
    specs += [
        (key, key, None)
        for key in (
            KEY_TOTAL_CHLORINE,
            KEY_TOTAL_ALKALINITY,
            KEY_CYANURIC_ACID,
            KEY_CALCIUM_HARDNESS,
        )
        if key in allowed
    ]

    readings: dict[str, Any] = {}
    for chart_key, value_key, conf_key in specs:
        manual = []
        for record in tracker.records:
            if value_key not in record.get("data", {}):
                continue
            logged_at = dt_util.parse_datetime(record.get("logged_at") or "")
            if logged_at and logged_at >= start:
                manual.append({"t": record["logged_at"], "v": record["data"][value_key]})
        series: dict[str, Any] = {}
        if manual:
            series["manual"] = manual
        entity_id = entry.options.get(conf_key) if conf_key else None
        if entity_id and (sensor_points := await _daily_means(hass, entity_id, start)):
            series["sensor"] = sensor_points
        if series:
            if conf_key is None:
                series["unit"] = "ppm"
            else:
                series["unit"] = "" if chart_key == "ph" else _unit_of(hass, entry, chart_key)
            readings[chart_key] = series

    # Role entities are charted too, so picking a heat pump as a role does
    # not cost you its runtime history.
    charted: list[str] = []
    # A schedule helper has no history worth charting, but the sensor that
    # reports whether the filtration is running most certainly does.
    for conf_key in (*EQUIPMENT_ROLES.values(), CONF_FILTRATION_STATE_ENTITY):
        if (entity_id := entry.options.get(conf_key)) and entity_id not in charted:
            charted.append(entity_id)
    for entity_id in entry.options.get(CONF_REPORT_SENSORS, ()):
        if entity_id not in charted:
            charted.append(entity_id)

    extra = []
    for entity_id in charted:
        state = hass.states.get(entity_id)
        name = (state.attributes.get("friendly_name") if state else None) or entity_id
        domain = entity_id.split(".")[0]
        if domain == "schedule":
            # Schedules are configuration, not history — charting when they
            # were "on" is meaningless; the report tab shows the next change.
            continue
        if domain in ONOFF_DOMAINS or (state and state.state in ("on", "off")):
            # Runtime, not readings: a heat pump charts the hours it spent
            # heating. Limited by the recorder retention window.
            points = await _ontime_daily(hass, entity_id, max(start, end - timedelta(days=31)), end)
            if any(point["v"] for point in points):
                extra.append({"type": "ontime", "name": name, "points": points})
        elif points := await _daily_means(hass, entity_id, start):
            unit = state.attributes.get("unit_of_measurement", "") if state else ""
            extra.append({"type": "line", "name": name, "unit": unit or "", "points": points})

    return {"days": days, "readings": readings, "extra": extra}


def _unit_of(hass: HomeAssistant, entry: ConfigEntry, live_key: str) -> str:
    entity_id = entry.options.get(LINKED_SOURCES[live_key])
    if entity_id and (state := hass.states.get(entity_id)):
        return state.attributes.get("unit_of_measurement") or ""
    defaults = {"free_chlorine": "ppm", "salt": "g/L", "temperature": "°C"}
    return defaults.get(live_key, "")
