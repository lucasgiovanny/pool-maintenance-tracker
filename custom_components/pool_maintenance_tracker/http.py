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
from pathlib import Path
from typing import TYPE_CHECKING, Any

from aiohttp import web
from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_LANGUAGE,
    CONF_PEOPLE,
    DATA_PAGE_TEMPLATE,
    DATA_RATE_LIMITER,
    DATA_TOKENS,
    DATA_VIEWS_REGISTERED,
    DEFAULT_LANGUAGE,
    DOMAIN,
    KEY_ACID_TANK_LEVEL,
    LINKED_SOURCES,
    MAX_BODY_SIZE,
    NUMBER_RANGES,
    URL_LOG,
    URL_PAGE,
)
from .modules import enabled_tiles, enabled_value_keys
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
    people.append(technician_label)
    return people


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

        try:
            result = process_payload(payload, entry.options)
        except PayloadError:
            return self.json({"ok": False, "error": "invalid_payload"}, status_code=400)

        runtime = entry.runtime_data
        tracker = runtime.tracker
        acid_alert = (
            result.values.get(KEY_ACID_TANK_LEVEL) == "quarter"
            and tracker.values.get(KEY_ACID_TANK_LEVEL) != "quarter"
        )
        # Audit trail: what the linked automatic sensors read at log time.
        if snapshot := {key: item["value"] for key, item in _live_values(hass, entry).items()}:
            result.record["snapshot"] = snapshot
        tracker.async_apply(result)
        if acid_alert:
            await runtime.reminders.async_send_acid_alert()

        _LOGGER.debug(
            "Accepted record for %s from %s (ignored: %s)",
            entry.title,
            result.record["person"],
            result.ignored,
        )
        return self.json({"ok": True, "ignored": result.ignored})
