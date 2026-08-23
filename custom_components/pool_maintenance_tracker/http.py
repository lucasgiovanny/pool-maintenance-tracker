"""Public HTTP endpoints: the maintenance page and the log receiver.

Both views are unauthenticated by design — the page is opened from a QR
code/NFC tag by people without HA accounts. Access control relies on the
non-guessable 256-bit token in the path, constant-time token comparison,
rate limiting, and the fact that what the endpoints accept is maintenance
state, not commands: every value here is something somebody declares about
the pool.

The one exception is deliberate, and worth stating plainly. A maintenance
visit can ask the equipment to move — the pool system off while the technician
works, the heat pump on — and that request is carried out. It is contained by
the role list: the page sends a role, never an entity id, so it only ever
reaches the entities the owner assigned to this pool in the options. The
acting itself lives in ``maintenance.py``.
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from time import monotonic
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.util import dt as dt_util

from . import filter_pressure, maintenance
from .const import (
    ACID_ALERT_LEVELS,
    COMBINED_CHLORINE_ALERT,
    CONF_FILTRATION_OFF_TIME_ENTITY,
    CONF_FILTRATION_ON_TIME_ENTITY,
    CONF_FILTRATION_SCHEDULE_ENTITY,
    CONF_FILTRATION_STATE_ENTITY,
    CONF_KIOSK_ENABLED,
    CONF_LANGUAGE,
    CONF_LINKED_MODE,
    CONF_PEOPLE,
    CONF_POOL_TYPE,
    CONF_POOL_VOLUME,
    CONF_REPORT_ENABLED,
    CONF_REPORT_SENSORS,
    CONF_SALT_TARGET_MAX,
    CONF_SALT_TARGET_MIN,
    CONF_TEMPERATURE_SOURCE,
    DATA_PAGE_TEMPLATE,
    DATA_RATE_LIMITER,
    DATA_TOKENS,
    DATA_VIEWS_REGISTERED,
    DEFAULT_KIOSK_ENABLED,
    DEFAULT_LANGUAGE,
    DEFAULT_REPORT_ENABLED,
    DEFAULT_SALT_TARGET_MAX,
    DEFAULT_SALT_TARGET_MIN,
    DOMAIN,
    EQUIPMENT_ROLES,
    HISTORY_PERIODS,
    IDEAL_CALCIUM_HARDNESS,
    IDEAL_CYANURIC,
    IDEAL_CYANURIC_SALT,
    IDEAL_FREE_CHLORINE,
    IDEAL_PH,
    IDEAL_TOTAL_ALKALINITY,
    KEY_ACID_TANK_LEVEL,
    KEY_CALCIUM_HARDNESS,
    KEY_COMBINED_CHLORINE,
    KEY_CYANURIC_ACID,
    KEY_FREE_CHLORINE,
    KEY_PH,
    KEY_SALT_LEVEL,
    KEY_TOTAL_ALKALINITY,
    KEY_TOTAL_CHLORINE,
    LINKED_MODE_MANUAL,
    LINKED_MODE_ON_RECORD,
    LINKED_SOURCES,
    LINKED_VALUE_KEYS,
    MAINTENANCE_ROLES,
    MAX_BODY_SIZE,
    MAX_NOTE_LENGTH,
    MAX_PERSON_LENGTH,
    NUMBER_RANGES,
    ONOFF_DOMAINS,
    POOL_TYPE_SALT,
    RECENT_RECORDS_ATTR_COUNT,
    ROLE_FILTRATION_SCHEDULE,
    SCHEDULE_MODE_HELPER,
    SCHEDULE_MODE_TIMES,
    THERMOSTAT_DOMAINS,
    TS_ANY,
    UNAVAILABLE_STATES,
    URL_HISTORY,
    URL_KIOSK,
    URL_LOG,
    URL_MANUAL,
    URL_MODE,
    URL_PAGE,
    URL_STATE,
    equipment_on,
    maintenance_values,
    schedule_mode,
)
from .entity import page_url
from .modules import (
    enabled_reminders,
    enabled_tiles,
    enabled_timestamp_keys,
    enabled_value_keys,
)
from .processor import PayloadError, process_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

    from .tracker import PoolTracker

_LOGGER = logging.getLogger(__name__)

CONFIG_MARKER = "__POOL_CONFIG__"
MANUAL_MARKER = "__MANUAL_CONFIG__"
PAGE_PATH = Path(__file__).parent / "frontend" / "page.html"
MANUAL_PATH = Path(__file__).parent / "frontend" / "manual.html"
KIOSK_PATH = Path(__file__).parent / "frontend" / "kiosk.html"
KIOSK_MARKER = "__KIOSK_CONFIG__"
STRINGS_DIR = Path(__file__).parent / "frontend" / "strings"

SECURITY_HEADERS = {
    "Cache-Control": "no-store",
    "X-Robots-Tag": "noindex, nofollow",
    "Referrer-Policy": "no-referrer",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": (
        "default-src 'none'; style-src 'unsafe-inline'; "
        "script-src 'unsafe-inline'; connect-src 'self'; img-src data:"
    ),
}

# (limit, window seconds) per bucket
LIMIT_POST_TOKEN = (30, 300)
LIMIT_POST_IP = (10, 60)
LIMIT_INVALID_IP = (20, 3600)


class RateLimiter:
    """Small in-memory sliding-window rate limiter."""

    def __init__(self) -> None:
        self._hits: dict[tuple[str, str], deque[float]] = defaultdict(deque)

    def allow(self, bucket: str, key: str, limit: int, window: float) -> bool:
        now = time.monotonic()
        hits = self._hits[(bucket, key)]
        while hits and now - hits[0] > window:
            hits.popleft()
        if len(hits) >= limit:
            return False
        hits.append(now)
        return True


@callback
def async_register_views(hass: HomeAssistant) -> None:
    """Register the public views once per HA instance."""
    domain_data = hass.data[DOMAIN]
    if domain_data.get(DATA_VIEWS_REGISTERED):
        return
    domain_data[DATA_RATE_LIMITER] = RateLimiter()
    hass.http.register_view(PoolPageView())
    hass.http.register_view(PoolLogView())
    hass.http.register_view(PoolHistoryView())
    hass.http.register_view(PoolManualView())
    hass.http.register_view(PoolStateView())
    hass.http.register_view(PoolKioskView())
    hass.http.register_view(PoolModeView())
    domain_data[DATA_VIEWS_REGISTERED] = True


@callback
def _entry_for_token(hass: HomeAssistant, token: str) -> ConfigEntry | None:
    tokens: dict[str, str] = hass.data.get(DOMAIN, {}).get(DATA_TOKENS, {})
    for known_token, entry_id in tokens.items():
        if hmac.compare_digest(known_token, token):
            return hass.config_entries.async_get_entry(entry_id)
    return None


def _limiter(hass: HomeAssistant) -> RateLimiter:
    return hass.data[DOMAIN][DATA_RATE_LIMITER]


def _report_on(entry: ConfigEntry) -> bool:
    return bool(entry.options.get(CONF_REPORT_ENABLED, DEFAULT_REPORT_ENABLED))


def _kiosk_on(entry: ConfigEntry) -> bool:
    return bool(entry.options.get(CONF_KIOSK_ENABLED, DEFAULT_KIOSK_ENABLED))


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


def _clean_person(raw: Any) -> str:
    person = raw.strip() if isinstance(raw, str) else ""
    if not person or len(person) > MAX_PERSON_LENGTH:
        return "unknown"
    return person


def _clean_note(raw: Any) -> str | None:
    """Return the normalized note text, or None when unusable."""
    if not isinstance(raw, str):
        return None
    text = raw.strip()
    if not text or len(text) > MAX_NOTE_LENGTH:
        return None
    return text


def _check_token(
    hass: HomeAssistant, request: web.Request, token: str
) -> ConfigEntry | web.Response:
    """Resolve the token or build the error response."""
    ip = request.remote or "unknown"
    # The token map only contains entries that are currently set up, so a
    # hit here implies runtime_data is available.
    entry = _entry_for_token(hass, token)
    if entry is None:
        if not _limiter(hass).allow("invalid", ip, *LIMIT_INVALID_IP):
            return web.Response(status=429)
        return web.Response(status=404)
    return entry


async def _load_page_template(hass: HomeAssistant) -> str:
    domain_data = hass.data[DOMAIN]
    if (template := domain_data.get(DATA_PAGE_TEMPLATE)) is None:
        template = await hass.async_add_executor_job(PAGE_PATH.read_text, "utf-8")
        domain_data[DATA_PAGE_TEMPLATE] = template
    return template


async def _load_strings(hass: HomeAssistant, language: str) -> dict[str, Any]:
    path = STRINGS_DIR / f"{language}.json"
    if not path.exists():
        path = STRINGS_DIR / f"{DEFAULT_LANGUAGE}.json"
    raw = await hass.async_add_executor_job(path.read_text, "utf-8")
    return json.loads(raw)


async def _page_people(hass: HomeAssistant, entry: ConfigEntry, technician_label: str) -> list[str]:
    """Selected HA users plus a generic technician chip.

    The ``people_users`` option limits which users appear; empty or absent
    means every active human user.
    """
    selected_ids = set(entry.options.get(CONF_PEOPLE, ()))
    people: list[str] = []
    for user in await hass.auth.async_get_users():
        if (
            user.is_active
            and not user.system_generated
            and user.name
            and user.name not in people
            and (not selected_ids or user.id in selected_ids)
        ):
            people.append(user.name)
    people.sort(key=str.casefold)
    # Technician comes first and is therefore pre-selected on the page —
    # the most common visitor without an HA account.
    return [technician_label, *people]


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
        # Not a target to aim for — anything up to the alert level is fine,
        # above it the water needs a shock.
        KEY_COMBINED_CHLORINE: {"min": 0.0, "max": COMBINED_CHLORINE_ALERT},
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


# Task order on the report tab
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


async def _build_page_config(hass: HomeAssistant, entry: ConfigEntry, token: str) -> dict[str, Any]:
    language = entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
    strings = await _load_strings(hass, language)
    technician_label = strings.get("technician", "Technician")
    return {
        "version": 2,
        "endpoint": URL_LOG.format(token=token),
        "pool_name": entry.title,
        "language": language,
        "people": await _page_people(hass, entry, technician_label),
        "tiles": enabled_tiles(entry.options),
        "strings": strings,
        "live": _live_values(hass, entry),
        "ranges": _ideal_ranges(entry),
        "volume": entry.options.get(CONF_POOL_VOLUME),
        "linked_mode": entry.options.get(CONF_LINKED_MODE, LINKED_MODE_MANUAL),
        "history_endpoint": URL_HISTORY.format(token=token),
        "state_endpoint": URL_STATE.format(token=token),
        "manual_endpoint": URL_MANUAL.format(token=token),
        "mode_endpoint": URL_MODE.format(token=token),
        # Top level, not inside the report: the flag and the sheet are offered
        # even when the status tab is switched off.
        "maintenance_mode": _maintenance_mode(entry),
        "maintenance_equipment": _maintenance_equipment(hass, entry),
        "history_periods": list(HISTORY_PERIODS),
        "report": (
            await _build_report(hass, entry)
            if entry.options.get(CONF_REPORT_ENABLED, DEFAULT_REPORT_ENABLED)
            else None
        ),
        # Only enabled value keys — the page uses presence here to decide
        # which steppers to render (e.g. the salt reading field).
        "limits": {
            key: {"min": low, "max": high, "step": step}
            for key, (low, high, step) in NUMBER_RANGES.items()
            if key in enabled_value_keys(entry.options)
        },
    }


class PoolPageView(HomeAssistantView):
    """Serve the maintenance page with the entry config injected."""

    url = URL_PAGE
    name = "api:pool_maintenance_tracker:page"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        template = await _load_page_template(hass)
        config = await _build_page_config(hass, entry, token)
        config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
        html = template.replace(f'"{CONFIG_MARKER}"', config_json)
        return web.Response(
            text=html,
            content_type="text/html",
            charset="utf-8",
            headers=SECURITY_HEADERS,
        )


class PoolLogView(HomeAssistantView):
    """Receive maintenance records posted by the page."""

    url = URL_LOG
    name = "api:pool_maintenance_tracker:log"
    requires_auth = False

    async def post(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        ip = request.remote or "unknown"
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry

        limiter = _limiter(hass)
        if not limiter.allow("post_ip", ip, *LIMIT_POST_IP) or not limiter.allow(
            "post_token", token, *LIMIT_POST_TOKEN
        ):
            return self.json({"ok": False, "error": "rate_limited"}, status_code=429)

        if request.content_type != "application/json":
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        body = await request.content.read(MAX_BODY_SIZE + 1)
        if len(body) > MAX_BODY_SIZE:
            return self.json({"ok": False, "error": "payload_too_large"}, status_code=400)
        try:
            payload = json.loads(body)
        except ValueError:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)

        runtime = entry.runtime_data
        tracker = runtime.tracker

        note_raw = payload.get("note") if isinstance(payload, dict) else None
        note_text = _clean_note(note_raw)

        try:
            result = process_payload(payload, entry.options)
        except PayloadError:
            if note_text:
                # Note-only submission: no record, no event, just the diary.
                tracker.async_add_note(_clean_person(payload.get("person")), note_text)
                return self.json({"ok": True, "ignored": []})
            return self.json({"ok": False, "error": "invalid_payload"}, status_code=400)

        if note_raw is not None and note_text is None:
            result.ignored.append("note")
        # Notify on the way down only: repeating "still low" every log is noise
        acid_alert = (
            result.values.get(KEY_ACID_TANK_LEVEL) in ACID_ALERT_LEVELS
            and tracker.values.get(KEY_ACID_TANK_LEVEL) not in ACID_ALERT_LEVELS
        )
        # Audit trail: what the linked automatic sensors read at log time.
        live = _live_values(hass, entry)
        if snapshot := {key: item["value"] for key, item in live.items()}:
            result.record["snapshot"] = snapshot
        # In fill_on_record mode, probe values fill entities the person did
        # not measure manually; manual readings always win.
        if entry.options.get(CONF_LINKED_MODE, LINKED_MODE_MANUAL) == LINKED_MODE_ON_RECORD:
            allowed = enabled_value_keys(entry.options)
            for live_key, item in live.items():
                value_key = LINKED_VALUE_KEYS.get(live_key)
                if not value_key or value_key not in allowed or value_key in result.values:
                    continue
                minimum, maximum, _step = NUMBER_RANGES[value_key]
                if minimum <= item["value"] <= maximum:
                    result.values[value_key] = item["value"]
        tracker.async_apply(result)
        if note_text:
            tracker.async_add_note(
                result.record["person"], note_text, created_at=result.record["logged_at"]
            )
        if acid_alert:
            await runtime.reminders.async_send_acid_alert(result.values[KEY_ACID_TANK_LEVEL])

        _LOGGER.debug(
            "Accepted record for %s from %s (ignored: %s)",
            entry.title,
            result.record["person"],
            result.ignored,
        )
        return self.json({"ok": True, "ignored": result.ignored})


class PoolHistoryView(HomeAssistantView):
    """Serve time series for the page's history tab."""

    url = URL_HISTORY
    name = "api:pool_maintenance_tracker:history"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        if not entry.options.get(CONF_REPORT_ENABLED, DEFAULT_REPORT_ENABLED):
            return web.Response(status=404)

        if not _limiter(hass).allow("history", token, 20, 300):
            return self.json({"ok": False, "error": "rate_limited"}, status_code=429)

        try:
            days = int(request.query.get("days", "30"))
        except ValueError:
            days = 0
        if days not in HISTORY_PERIODS:
            return self.json({"ok": False, "error": "invalid_period"}, status_code=400)

        data = await _build_history(hass, entry, days)
        return self.json(data)


class PoolManualView(HomeAssistantView):
    """Serve the printable machine-room manual (QR + NFC space + steps)."""

    url = URL_MANUAL
    name = "api:pool_maintenance_tracker:manual"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry

        import segno

        language = entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        strings = await _load_strings(hass, language)
        url = page_url(hass, entry) or URL_PAGE.format(token=token)
        qr_data_uri = await hass.async_add_executor_job(
            lambda: segno.make(url, error="m").png_data_uri(scale=10, border=2)
        )
        config = {
            "language": language,
            "pool_name": entry.title,
            "url": url,
            "qr": qr_data_uri,
            "strings": strings.get("manual", {}),
        }
        template = await hass.async_add_executor_job(MANUAL_PATH.read_text, "utf-8")
        config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
        html = template.replace(f'"{MANUAL_MARKER}"', config_json)
        headers = dict(SECURITY_HEADERS)
        # The QR is embedded as a data: URI image.
        return web.Response(text=html, content_type="text/html", charset="utf-8", headers=headers)


class PoolStateView(HomeAssistantView):
    """Fresh live values and report snapshot for the page's auto-refresh."""

    url = URL_STATE
    name = "api:pool_maintenance_tracker:state"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        # Both the status tab and the kiosk screen live off this endpoint.
        if not (_report_on(entry) or _kiosk_on(entry)):
            return web.Response(status=404)
        if not _limiter(hass).allow("state", token, 60, 300):
            return self.json({"ok": False, "error": "rate_limited"}, status_code=429)
        return self.json(
            {
                "live": _live_values(hass, entry),
                "report": await _build_report(hass, entry),
                "temperature": await _temperature_trend(hass, entry),
                "maintenance_mode": _maintenance_mode(entry),
            }
        )


class PoolModeView(HomeAssistantView):
    """Start and end a maintenance visit from the page.

    The technician standing at the machine room has the page open and no Home
    Assistant account, so this is the only way they can say "I am working on
    it, put the system there, and give me an hour". Starting carries out the
    plan and reports back what moved; ending puts it back. Both are contained
    by the role list — a payload names ``pool_system``, never an entity id.
    """

    url = URL_MODE
    name = "api:pool_maintenance_tracker:mode"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        """The flag on its own, for the page to poll.

        The status tab is optional and the state endpoint goes with it, so
        without this the page would have no way to notice a window running
        out or somebody else ending the visit.
        """
        hass = request.app[KEY_HASS]
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        if not maintenance.is_enabled(entry):
            return web.Response(status=404)
        if not _limiter(hass).allow("mode", token, 60, 300):
            return self.json({"ok": False, "error": "rate_limited"}, status_code=429)
        return self.json({"ok": True, **_maintenance_mode(entry)})

    async def post(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        ip = request.remote or "unknown"
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        if not maintenance.is_enabled(entry):
            return web.Response(status=404)

        limiter = _limiter(hass)
        if not limiter.allow("post_ip", ip, *LIMIT_POST_IP) or not limiter.allow(
            "post_token", token, *LIMIT_POST_TOKEN
        ):
            return self.json({"ok": False, "error": "rate_limited"}, status_code=429)

        if request.content_type != "application/json":
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        body = await request.content.read(MAX_BODY_SIZE + 1)
        if len(body) > MAX_BODY_SIZE:
            return self.json({"ok": False, "error": "payload_too_large"}, status_code=400)
        try:
            payload = json.loads(body)
        except ValueError:
            return self.json({"ok": False, "error": "invalid_json"}, status_code=400)
        if not isinstance(payload, dict) or not isinstance(payload.get("on"), bool):
            return self.json({"ok": False, "error": "invalid_payload"}, status_code=400)

        on = payload["on"]
        try:
            until = maintenance.parse_minutes(payload.get("minutes")) if on else None
            plan, ignored = (
                maintenance.clean_plan(hass, entry, payload.get("equipment")) if on else ({}, [])
            )
        except maintenance.PlanError:
            return self.json({"ok": False, "error": "invalid_payload"}, status_code=400)

        tracker = entry.runtime_data.tracker
        person = _clean_person(payload.get("person"))
        tracker.async_set_maintenance_mode(on, person, until=until, plan=plan)
        _LOGGER.debug(
            "Maintenance mode %s for %s by %s (until %s, plan %s)",
            "on" if on else "off",
            entry.title,
            tracker.maintenance_mode_by,
            until,
            plan,
        )
        # Starting is carried out inside the request on purpose: it is the
        # only way the page can tell the technician what actually moved.
        # Ending is not — the session already restores on the flag dropping,
        # from wherever it was dropped, and it gets there first.
        result = await maintenance.async_apply(hass, entry, plan) if on else {}
        return self.json({"ok": True, **_maintenance_mode(entry), **result, "ignored": ignored})


class PoolKioskView(HomeAssistantView):
    """Display-only dashboard for a screen next to the pool."""

    url = URL_KIOSK
    name = "api:pool_maintenance_tracker:kiosk"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        if not _kiosk_on(entry):
            return web.Response(status=404)

        language = entry.options.get(CONF_LANGUAGE, DEFAULT_LANGUAGE)
        import segno

        url = page_url(hass, entry) or URL_PAGE.format(token=token)
        config = {
            "pool_name": entry.title,
            "language": language,
            "strings": await _load_strings(hass, language),
            "state_endpoint": URL_STATE.format(token=token),
            "live": _live_values(hass, entry),
            "report": await _build_report(hass, entry),
            "temperature": await _temperature_trend(hass, entry),
            "qr": await hass.async_add_executor_job(
                lambda: segno.make(url, error="m").png_data_uri(scale=6, border=2)
            ),
        }
        template = await hass.async_add_executor_job(KIOSK_PATH.read_text, "utf-8")
        config_json = json.dumps(config, ensure_ascii=False).replace("</", "<\\/")
        html = template.replace(f'"{KIOSK_MARKER}"', config_json)
        return web.Response(
            text=html,
            content_type="text/html",
            charset="utf-8",
            headers=SECURITY_HEADERS,
        )
