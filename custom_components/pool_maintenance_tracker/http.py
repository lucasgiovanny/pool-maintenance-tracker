"""Public HTTP endpoints: the maintenance page and the log receiver.

Both views are unauthenticated by design — the page is opened from a QR
code/NFC tag by people without HA accounts. Access control relies on the
non-guessable 256-bit token in the path, constant-time token comparison,
rate limiting, and the fact that the endpoints only accept declarative
maintenance state (they can never command equipment).
"""

from __future__ import annotations

import hmac
import json
import logging
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback
from homeassistant.util import dt as dt_util

from .const import (
    CONF_LANGUAGE,
    CONF_LINKED_MODE,
    CONF_PEOPLE,
    CONF_REPORT_ENABLED,
    CONF_REPORT_SENSORS,
    DATA_PAGE_TEMPLATE,
    DATA_RATE_LIMITER,
    DATA_TOKENS,
    DATA_VIEWS_REGISTERED,
    DEFAULT_LANGUAGE,
    DEFAULT_REPORT_ENABLED,
    DOMAIN,
    HISTORY_PERIODS,
    KEY_ACID_TANK_LEVEL,
    LINKED_MODE_MANUAL,
    LINKED_MODE_ON_RECORD,
    LINKED_SOURCES,
    LINKED_VALUE_KEYS,
    MAX_BODY_SIZE,
    MAX_NOTE_LENGTH,
    MAX_PERSON_LENGTH,
    NUMBER_RANGES,
    RECENT_RECORDS_ATTR_COUNT,
    TS_ANY,
    URL_HISTORY,
    URL_LOG,
    URL_NOTE,
    URL_PAGE,
)
from .modules import (
    enabled_reminders,
    enabled_tiles,
    enabled_timestamp_keys,
    enabled_value_keys,
)
from .processor import PayloadError, process_payload

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry

_LOGGER = logging.getLogger(__name__)

CONFIG_MARKER = "__POOL_CONFIG__"
PAGE_PATH = Path(__file__).parent / "frontend" / "page.html"
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
    hass.http.register_view(PoolNoteView())
    hass.http.register_view(PoolHistoryView())
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
            "value": round(value, 2),
            "unit": state.attributes.get("unit_of_measurement") or "",
        }
    return live


# Task order on the report tab
REPORT_TASK_ORDER = (
    "water_test",
    "salt_added",
    "filter_wash",
    "cell_clean",
    "probe_calibration",
    "acid_refill",
    "cleaning",
)


@callback
def _build_report(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
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
            "person": item.get("person"),
            "logged_at": item.get("logged_at"),
            "categories": item.get("categories", []),
            "data": item.get("data", {}),
            "snapshot": item.get("snapshot", {}),
        }
        for item in reversed(tracker.records[-RECENT_RECORDS_ATTR_COUNT:])
    ]

    extra = []
    for entity_id in entry.options.get(CONF_REPORT_SENSORS, ()):
        state = hass.states.get(entity_id)
        if state is None or state.state in ("unknown", "unavailable"):
            continue
        extra.append(
            {
                "entity_id": entity_id,
                "name": state.attributes.get("friendly_name") or entity_id,
                "state": state.state,
                "unit": state.attributes.get("unit_of_measurement") or "",
                "domain": entity_id.split(".")[0],
                "last_changed": state.last_changed.isoformat(),
            }
        )

    return {
        "values": values,
        "tasks": tasks,
        "last_maintenance": tracker.timestamps.get(TS_ANY),
        "records": records,
        "notes": list(reversed(tracker.notes)),
        "extra": extra,
    }


ONOFF_DOMAINS = {"binary_sensor", "switch", "input_boolean", "light"}


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


def _ontime_buckets(changes, start, end) -> list[dict[str, Any]]:
    """Hours 'on' per local day from a list of (moment, state) changes.

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
        if state != "on":
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
    return _ontime_buckets(sorted(changes), start, end)


async def _build_history(hass: HomeAssistant, entry: ConfigEntry, days: int) -> dict[str, Any]:
    """Time series for the page's history tab."""
    tracker = entry.runtime_data.tracker
    end = dt_util.utcnow()
    start = end - timedelta(days=days)

    readings: dict[str, Any] = {}
    for live_key, conf_key in LINKED_SOURCES.items():
        value_key = LINKED_VALUE_KEYS[live_key]
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
        entity_id = entry.options.get(conf_key)
        if entity_id and (sensor_points := await _daily_means(hass, entity_id, start)):
            series["sensor"] = sensor_points
        if series:
            series["unit"] = "" if live_key == "ph" else _unit_of(hass, entry, live_key)
            readings[live_key] = series

    extra = []
    for entity_id in entry.options.get(CONF_REPORT_SENSORS, ()):
        state = hass.states.get(entity_id)
        name = (state.attributes.get("friendly_name") if state else None) or entity_id
        domain = entity_id.split(".")[0]
        if domain in ONOFF_DOMAINS or (state and state.state in ("on", "off")):
            # On/off runtime is limited by the recorder retention window.
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
        "linked_mode": entry.options.get(CONF_LINKED_MODE, LINKED_MODE_MANUAL),
        "note_endpoint": URL_NOTE.format(token=token),
        "history_endpoint": URL_HISTORY.format(token=token),
        "history_periods": list(HISTORY_PERIODS),
        "report": (
            _build_report(hass, entry)
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
        acid_alert = (
            result.values.get(KEY_ACID_TANK_LEVEL) == "quarter"
            and tracker.values.get(KEY_ACID_TANK_LEVEL) != "quarter"
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
            await runtime.reminders.async_send_acid_alert()

        _LOGGER.debug(
            "Accepted record for %s from %s (ignored: %s)",
            entry.title,
            result.record["person"],
            result.ignored,
        )
        return self.json({"ok": True, "ignored": result.ignored})


class PoolNoteView(HomeAssistantView):
    """Receive standalone notes posted from the report tab."""

    url = URL_NOTE
    name = "api:pool_maintenance_tracker:note"
    requires_auth = False

    async def post(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        ip = request.remote or "unknown"
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        # The notes card only exists on the report tab.
        if not entry.options.get(CONF_REPORT_ENABLED, DEFAULT_REPORT_ENABLED):
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

        if not isinstance(payload, dict) or (text := _clean_note(payload.get("text"))) is None:
            return self.json({"ok": False, "error": "invalid_note"}, status_code=400)

        note = entry.runtime_data.tracker.async_add_note(_clean_person(payload.get("person")), text)
        return self.json({"ok": True, "note": note})


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
