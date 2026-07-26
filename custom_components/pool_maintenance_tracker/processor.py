"""Payload v2 validation and record building.

Pure logic, no I/O. Validation semantics: every field is optional;
``null``/absent fields are no-ops; out-of-range or wrong-typed values are
silently dropped but echoed in the ``ignored`` list; sections belonging to
disabled modules are ignored; a payload with nothing valid left is
rejected.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from homeassistant.util import dt as dt_util
from homeassistant.util import ulid as ulid_util

from .const import (
    ACID_TANK_LEVELS,
    CATEGORY_ACID_REFILL,
    CATEGORY_CELL_CLEAN,
    CATEGORY_CLEANING,
    CATEGORY_FILTER_WASH,
    CATEGORY_PROBE_CALIBRATION,
    CATEGORY_SALT,
    CATEGORY_WATER_TEST,
    CHLORINATOR_MODES,
    CLEANING_TYPES,
    KEY_ACID_TANK_LEVEL,
    KEY_CHLORINATOR_MODE,
    KEY_CHLORINATOR_OUTPUT,
    KEY_FREE_CHLORINE,
    KEY_PH,
    KEY_SALT_ADDED,
    KEY_SALT_LEVEL,
    KEY_WATER_TEMPERATURE,
    MAX_PERSON_LENGTH,
    NUMBER_RANGES,
    TS_ACID_REFILL,
    TS_ANY,
    TS_CELL_CLEAN,
    TS_CLEANING,
    TS_FILTER_WASH,
    TS_PROBE_CALIBRATION,
    TS_SALT_ADDED,
    TS_WATER_TEST,
)
from .modules import enabled_categories, enabled_value_keys

LOGGED_AT_PAST_WINDOW = timedelta(days=7)
LOGGED_AT_FUTURE_WINDOW = timedelta(hours=1)

# category -> timestamp updated when that category is logged
CATEGORY_TIMESTAMPS = {
    CATEGORY_WATER_TEST: TS_WATER_TEST,
    CATEGORY_SALT: TS_SALT_ADDED,
    CATEGORY_FILTER_WASH: TS_FILTER_WASH,
    CATEGORY_CELL_CLEAN: TS_CELL_CLEAN,
    CATEGORY_PROBE_CALIBRATION: TS_PROBE_CALIBRATION,
    CATEGORY_ACID_REFILL: TS_ACID_REFILL,
    CATEGORY_CLEANING: TS_CLEANING,
}


class PayloadError(Exception):
    """Raised when a payload contains nothing valid."""


@dataclass
class ProcessResult:
    """Validated outcome of one submitted payload."""

    record: dict[str, Any]
    values: dict[str, Any] = field(default_factory=dict)
    timestamps: dict[str, str] = field(default_factory=dict)
    ignored: list[str] = field(default_factory=list)


def _valid_number(key: str, value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    minimum, maximum, _ = NUMBER_RANGES[key]
    number = float(value)
    if minimum <= number <= maximum:
        return round(number, 2)
    return None


def _resolve_logged_at(raw: Any, now: datetime) -> datetime:
    if not isinstance(raw, str):
        return now
    logged_at = dt_util.parse_datetime(raw)
    if logged_at is None or logged_at.tzinfo is None:
        return now
    if now - LOGGED_AT_PAST_WINDOW < logged_at < now + LOGGED_AT_FUTURE_WINDOW:
        return logged_at
    return now


def process_payload(
    payload: Any,
    options: Mapping[str, Any],
    now: datetime | None = None,
) -> ProcessResult:
    """Validate a submitted payload and build the resulting record.

    Raises PayloadError if nothing valid remains.
    """
    if not isinstance(payload, dict):
        raise PayloadError("payload must be a JSON object")

    now = now or dt_util.utcnow()
    allowed_categories = enabled_categories(options)
    allowed_values = enabled_value_keys(options)

    ignored: list[str] = []
    values: dict[str, Any] = {}
    data: dict[str, Any] = {}

    person_raw = payload.get("person")
    person = person_raw.strip() if isinstance(person_raw, str) else ""
    if not person or len(person) > MAX_PERSON_LENGTH:
        if person_raw is not None:
            ignored.append("person")
        person = "unknown"

    logged_at = _resolve_logged_at(payload.get("logged_at"), now)
    logged_at_iso = logged_at.isoformat()

    categories_raw = payload.get("categories")
    categories: list[str] = []
    if categories_raw is not None:
        if isinstance(categories_raw, list):
            for category in categories_raw:
                if isinstance(category, str) and category in allowed_categories:
                    if category not in categories:
                        categories.append(category)
                else:
                    ignored.append(f"categories.{category}")
        else:
            ignored.append("categories")

    def take_number(section: str, field_name: str, raw: Any, key: str) -> None:
        if raw is None:
            return
        if key not in allowed_values:
            ignored.append(f"{section}.{field_name}")
            return
        number = _valid_number(key, raw)
        if number is None:
            ignored.append(f"{section}.{field_name}")
            return
        values[key] = number
        data[key] = number

    def take_enum(section: str, field_name: str, raw: Any, key: str, allowed: list[str]) -> None:
        if raw is None:
            return
        if key not in allowed_values or raw not in allowed:
            ignored.append(f"{section}.{field_name}")
            return
        values[key] = raw
        data[key] = raw

    def section_dict(name: str) -> dict[str, Any]:
        raw = payload.get(name)
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            ignored.append(name)
            return {}
        return raw

    readings = section_dict("readings")
    take_number("readings", "ph", readings.get("ph"), KEY_PH)
    take_number("readings", "free_chlorine", readings.get("free_chlorine"), KEY_FREE_CHLORINE)
    take_number("readings", "salt", readings.get("salt"), KEY_SALT_LEVEL)
    take_number("readings", "temperature", readings.get("temperature"), KEY_WATER_TEMPERATURE)

    chlorinator = section_dict("chlorinator")
    take_number("chlorinator", "output", chlorinator.get("output"), KEY_CHLORINATOR_OUTPUT)
    take_enum(
        "chlorinator",
        "mode",
        chlorinator.get("mode"),
        KEY_CHLORINATOR_MODE,
        CHLORINATOR_MODES,
    )

    salt = section_dict("salt")
    take_number("salt", "added_kg", salt.get("added_kg"), KEY_SALT_ADDED)

    acid = section_dict("acid")
    take_enum("acid", "level", acid.get("level"), KEY_ACID_TANK_LEVEL, ACID_TANK_LEVELS)

    cleaning = section_dict("cleaning")
    cleaning_types_raw = cleaning.get("types")
    if cleaning_types_raw is not None:
        if CATEGORY_CLEANING in allowed_categories and isinstance(cleaning_types_raw, list):
            cleaning_types = [
                item
                for item in cleaning_types_raw
                if isinstance(item, str) and item in CLEANING_TYPES
            ]
            for item in cleaning_types_raw:
                if not isinstance(item, str) or item not in CLEANING_TYPES:
                    ignored.append(f"cleaning.types.{item}")
            if cleaning_types:
                values["cleaning_types"] = cleaning_types
                data["cleaning_types"] = cleaning_types
        else:
            ignored.append("cleaning.types")

    if not categories and not data:
        raise PayloadError("nothing valid to record")

    timestamps: dict[str, str] = {TS_ANY: logged_at_iso}
    for category in categories:
        if (ts_key := CATEGORY_TIMESTAMPS.get(category)) is not None:
            timestamps[ts_key] = logged_at_iso
    # Data presence also refreshes the matching timestamps, even when the
    # corresponding category chip was not selected on the page.
    if any(
        key in data for key in (KEY_PH, KEY_FREE_CHLORINE, KEY_SALT_LEVEL, KEY_WATER_TEMPERATURE)
    ):
        timestamps[TS_WATER_TEST] = logged_at_iso
    if KEY_SALT_ADDED in data:
        timestamps[TS_SALT_ADDED] = logged_at_iso
    if KEY_ACID_TANK_LEVEL in data:
        timestamps[TS_ACID_REFILL] = logged_at_iso
    if "cleaning_types" in data:
        timestamps[TS_CLEANING] = logged_at_iso

    record = {
        "id": ulid_util.ulid_now(),
        "person": person,
        "logged_at": logged_at_iso,
        "categories": categories,
        "data": data,
    }
    return ProcessResult(record=record, values=values, timestamps=timestamps, ignored=ignored)
