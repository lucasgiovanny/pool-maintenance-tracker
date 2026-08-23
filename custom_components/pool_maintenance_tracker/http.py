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

import csv
import hmac
import io
import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from . import maintenance
from .const import (
    ACID_ALERT_LEVELS,
    CONF_KIOSK_ENABLED,
    CONF_LANGUAGE,
    CONF_LINKED_MODE,
    CONF_PEOPLE,
    CONF_POOL_VOLUME,
    CONF_REPORT_ENABLED,
    DATA_PAGE_TEMPLATE,
    DATA_RATE_LIMITER,
    DATA_STRINGS_CACHE,
    DATA_TOKENS,
    DATA_VIEWS_REGISTERED,
    DEFAULT_KIOSK_ENABLED,
    DEFAULT_LANGUAGE,
    DEFAULT_REPORT_ENABLED,
    DOMAIN,
    HISTORY_PERIODS,
    KEY_ACID_TANK_LEVEL,
    KEY_CHLORINATOR_MODE,
    LINKED_MODE_MANUAL,
    LINKED_MODE_ON_RECORD,
    LINKED_VALUE_KEYS,
    MAX_BODY_SIZE,
    MAX_NOTE_LENGTH,
    MAX_PERSON_LENGTH,
    NUMBER_RANGES,
    URL_EXPORT,
    URL_HISTORY,
    URL_KIOSK,
    URL_LOG,
    URL_MANUAL,
    URL_MODE,
    URL_PAGE,
    URL_STATE,
)
from .entity import page_url
from .modules import (
    enabled_tiles,
    enabled_value_keys,
)
from .processor import PayloadError, process_payload
from .report import (
    _build_history,
    _build_report,
    _ideal_ranges,
    _live_values,
    _maintenance_equipment,
    _maintenance_mode,
    _temperature_trend,
)

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry


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
    hass.http.register_view(PoolExportView())
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
    """String bundle for one language, read from disk once per HA run.

    The page polls every 60 s and the kiosk every 30 s; the bundles only
    change with the integration itself, so cache them like the template.
    """
    cache: dict[str, dict[str, Any]] = hass.data[DOMAIN].setdefault(DATA_STRINGS_CACHE, {})
    if (strings := cache.get(language)) is not None:
        return strings
    path = STRINGS_DIR / f"{language}.json"
    if not path.exists():
        path = STRINGS_DIR / f"{DEFAULT_LANGUAGE}.json"
    raw = await hass.async_add_executor_job(path.read_text, "utf-8")
    strings = json.loads(raw)
    cache[language] = strings
    return strings


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


# Task order on the report tab


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
        "export_endpoint": URL_EXPORT.format(token=token),
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


class PoolExportView(HomeAssistantView):
    """The whole maintenance log as a CSV download.

    Same audience as the page itself: whoever holds the link logged these
    records and gets to take them home. One row per record, one column per
    value the pool has ever used, readable by any spreadsheet.
    """

    url = URL_EXPORT
    name = "api:pool_maintenance_tracker:export"
    requires_auth = False

    async def get(self, request: web.Request, token: str) -> web.Response:
        hass = request.app[KEY_HASS]
        entry = _check_token(hass, request, token)
        if isinstance(entry, web.Response):
            return entry
        if not _limiter(hass).allow("export", token, 10, 300):
            return web.Response(status=429)

        records = entry.runtime_data.tracker.records
        # Stable column order: the number keys as declared, then the enums,
        # then whatever else a record ever carried.
        known = [*NUMBER_RANGES, KEY_CHLORINATOR_MODE, KEY_ACID_TANK_LEVEL, "cleaning_types"]
        used = {key for record in records for key in record.get("data", {})}
        columns = [key for key in known if key in used]
        columns += sorted(used - set(columns))

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["id", "logged_at", "person", "categories", *columns])
        for record in records:
            data = record.get("data", {})
            writer.writerow(
                [
                    record.get("id", ""),
                    record.get("logged_at", ""),
                    record.get("person", ""),
                    ";".join(record.get("categories", [])),
                    *(
                        ";".join(value) if isinstance(value := data.get(key, ""), list) else value
                        for key in columns
                    ),
                ]
            )
        filename = f"{entry.title or 'pool'}-maintenance-log.csv".replace('"', "")
        return web.Response(
            text=buffer.getvalue(),
            content_type="text/csv",
            charset="utf-8",
            headers={
                **SECURITY_HEADERS,
                "Content-Disposition": f'attachment; filename="{filename}"',
            },
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
