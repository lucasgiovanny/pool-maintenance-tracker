"""Constants for the Pool Maintenance Tracker integration."""

from __future__ import annotations

from typing import Final

DOMAIN: Final = "pool_maintenance_tracker"

# Config entry data (immutable after creation)
CONF_TOKEN: Final = "token"

# Options (editable via the options flow)
CONF_POOL_TYPE: Final = "pool_type"
CONF_MODULES: Final = "modules"
CONF_LANGUAGE: Final = "language"
# HA user ids allowed on the page; empty/absent means all active users
CONF_PEOPLE: Final = "people_users"

# Linked external sensors (entity ids of e.g. a smart probe). Shown as live
# reference values on the page and snapshotted into each record.
CONF_PH_SOURCE: Final = "ph_source"
CONF_CHLORINE_SOURCE: Final = "chlorine_source"
CONF_SALT_SOURCE: Final = "salt_source"
CONF_TEMPERATURE_SOURCE: Final = "temperature_source"
LINKED_SOURCES: Final[dict[str, str]] = {
    # live-value key -> options key
    "ph": CONF_PH_SOURCE,
    "free_chlorine": CONF_CHLORINE_SOURCE,
    "salt": CONF_SALT_SOURCE,
    "temperature": CONF_TEMPERATURE_SOURCE,
}

# Whether the public page shows the read-only report tab
CONF_REPORT_ENABLED: Final = "report_enabled"
DEFAULT_REPORT_ENABLED: Final = True

# Extra entities (any integration) displayed on the report tab
CONF_REPORT_SENSORS: Final = "report_sensors"

# How linked sensors interact with the manual entities (per entry)
CONF_LINKED_MODE: Final = "linked_mode"
LINKED_MODE_MANUAL: Final = "manual_only"
LINKED_MODE_ON_RECORD: Final = "fill_on_record"
LINKED_MODE_MIRROR: Final = "mirror"
LINKED_MODES: Final = [LINKED_MODE_MANUAL, LINKED_MODE_ON_RECORD, LINKED_MODE_MIRROR]
CONF_NOTIFY_SERVICE: Final = "notify_service"
CONF_FILTER_DAYS: Final = "filter_days"
CONF_PROBE_DAYS: Final = "probe_days"
CONF_CELL_DAYS: Final = "cell_days"
CONF_REMINDER_TIME: Final = "reminder_time"

POOL_TYPE_SALT: Final = "salt"
POOL_TYPE_CHLORINE: Final = "chlorine"
POOL_TYPE_OTHER: Final = "other"
POOL_TYPES: Final = [POOL_TYPE_SALT, POOL_TYPE_CHLORINE, POOL_TYPE_OTHER]

LANGUAGES: Final = ["en", "pt", "es", "fr", "de", "it"]
DEFAULT_LANGUAGE: Final = "en"
DEFAULT_FILTER_DAYS: Final = 30
DEFAULT_PROBE_DAYS: Final = 60
DEFAULT_CELL_DAYS: Final = 90
DEFAULT_REMINDER_TIME: Final = "10:00"

# Value keys (tracker "values" bucket)
KEY_PH: Final = "ph"
KEY_FREE_CHLORINE: Final = "free_chlorine"
KEY_WATER_TEMPERATURE: Final = "water_temperature"
KEY_SALT_LEVEL: Final = "salt_level"
KEY_SALT_ADDED: Final = "salt_added"
KEY_CHLORINATOR_OUTPUT: Final = "chlorinator_output"
KEY_CHLORINATOR_MODE: Final = "chlorinator_mode"
KEY_ACID_TANK_LEVEL: Final = "acid_tank_level"

# Timestamp keys (tracker "timestamps" bucket)
TS_WATER_TEST: Final = "water_test"
TS_SALT_ADDED: Final = "salt_added"
TS_FILTER_WASH: Final = "filter_wash"
TS_CELL_CLEAN: Final = "cell_clean"
TS_PROBE_CALIBRATION: Final = "probe_calibration"
TS_ACID_REFILL: Final = "acid_refill"
TS_CLEANING: Final = "cleaning"
TS_ANY: Final = "any"

# Record categories accepted in payload v2
CATEGORY_WATER_TEST: Final = "water_test"
CATEGORY_CHLORINATOR: Final = "chlorinator"
CATEGORY_SALT: Final = "salt"
CATEGORY_FILTER_WASH: Final = "filter_wash"
CATEGORY_CELL_CLEAN: Final = "cell_clean"
CATEGORY_PROBE_CALIBRATION: Final = "probe_calibration"
CATEGORY_ACID_REFILL: Final = "acid_refill"
CATEGORY_CLEANING: Final = "cleaning"

# Enum values
CHLORINATOR_MODES: Final = ["smart", "manual", "boost"]
ACID_TANK_LEVELS: Final = ["full", "three_quarters", "half", "quarter"]
ACID_LEVEL_ALERT: Final = "quarter"
CLEANING_TYPES: Final = ["vacuum", "waterline", "baskets"]

# Validation ranges: key -> (min, max, step)
NUMBER_RANGES: Final[dict[str, tuple[float, float, float]]] = {
    KEY_PH: (6.0, 9.0, 0.1),
    KEY_FREE_CHLORINE: (0.0, 10.0, 0.5),
    KEY_WATER_TEMPERATURE: (0.0, 45.0, 0.1),
    KEY_SALT_LEVEL: (0.0, 10.0, 0.1),
    KEY_SALT_ADDED: (0.0, 500.0, 1.0),
    KEY_CHLORINATOR_OUTPUT: (0.0, 10.0, 0.5),
}

LINKED_VALUE_KEYS: Final[dict[str, str]] = {
    # live-value key -> manual entity value key
    "ph": KEY_PH,
    "free_chlorine": KEY_FREE_CHLORINE,
    "salt": KEY_SALT_LEVEL,
    "temperature": KEY_WATER_TEMPERATURE,
}

PAYLOAD_VERSION: Final = 2
MAX_PERSON_LENGTH: Final = 40
MAX_BODY_SIZE: Final = 16 * 1024  # bytes
MAX_RECORDS: Final = 200
MAX_NOTES: Final = 50
MAX_NOTE_LENGTH: Final = 500
RECENT_RECORDS_ATTR_COUNT: Final = 20

STORAGE_VERSION: Final = 1

# Event fired on the HA bus for every accepted record
EVENT_RECORD: Final = f"{DOMAIN}_record"

# hass.data[DOMAIN] keys
DATA_TOKENS: Final = "tokens"
DATA_VIEWS_REGISTERED: Final = "views_registered"
DATA_PAGE_TEMPLATE: Final = "page_template"
DATA_RATE_LIMITER: Final = "rate_limiter"
DATA_TRACKERS: Final = "trackers"

# Public HTTP endpoints (token is path-scoped)
URL_PAGE: Final = "/api/pool_maintenance_tracker/{token}/page"
URL_LOG: Final = "/api/pool_maintenance_tracker/{token}/log"
URL_HISTORY: Final = "/api/pool_maintenance_tracker/{token}/history"
URL_MANUAL: Final = "/api/pool_maintenance_tracker/{token}/manual"
URL_STATE: Final = "/api/pool_maintenance_tracker/{token}/state"
HISTORY_PERIODS: Final = (7, 30, 180)

TECHNICIAN_PERSON: Final = "technician"

# Re-notify damper for overdue reminders
RENOTIFY_DAYS: Final = 3


def signal_updated(entry_id: str) -> str:
    """Dispatcher signal fired when the tracker state for an entry changes."""
    return f"{DOMAIN}_{entry_id}_updated"


def signal_record(entry_id: str) -> str:
    """Dispatcher signal fired with each accepted maintenance record."""
    return f"{DOMAIN}_{entry_id}_record"
