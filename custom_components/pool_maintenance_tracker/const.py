"""Constants for the Pool Maintenance Tracker integration."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Final

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

# Display-only dashboard for a wall screen next to the pool
CONF_KIOSK_ENABLED: Final = "kiosk_enabled"
DEFAULT_KIOSK_ENABLED: Final = True

# Maintenance mode: a flag raised while somebody works on the pool. Nothing
# in here acts on it — it exists so that automations can (stop the pump,
# mute an alarm, skip a schedule), and so that whoever is standing at the
# machine room can raise it from the page. On by default, because a pool
# being worked on is a normal thing to want to know; switch it off in the
# options and the entity and every toggle go away with it.
CONF_MAINTENANCE_MODE: Final = "maintenance_mode_enabled"
DEFAULT_MAINTENANCE_MODE: Final = True
KEY_MAINTENANCE_MODE: Final = "maintenance_mode"

# Named equipment roles: explicitly picked entities the dashboards give a
# fixed place to, instead of guessing from the generic extra-entity list.
CONF_POOL_SYSTEM_ENTITY: Final = "pool_system_entity"
CONF_HEAT_PUMP_ENTITY: Final = "heat_pump_entity"
CONF_FILTRATION_SCHEDULE_ENTITY: Final = "filtration_schedule_entity"
CONF_PUMP_ENTITY: Final = "pump_entity"
CONF_POOL_LIGHT_ENTITY: Final = "pool_light_entity"
CONF_COVER_ENTITY: Final = "cover_entity"
EQUIPMENT_ROLES: Final[dict[str, str]] = {
    "pool_system": CONF_POOL_SYSTEM_ENTITY,
    "heat_pump": CONF_HEAT_PUMP_ENTITY,
    "filtration_schedule": CONF_FILTRATION_SCHEDULE_ENTITY,
    "pump": CONF_PUMP_ENTITY,
    "pool_light": CONF_POOL_LIGHT_ENTITY,
    "cover": CONF_COVER_ENTITY,
}
ROLE_FILTRATION_SCHEDULE: Final = "filtration_schedule"

# A pool says when it filters in one of two ways. Home Assistant's own
# schedule helper is the tidy one, and the one this integration started
# with. The other is a pool controller that already owns the schedule and
# publishes it as plain entities: the hour it starts, the hour it stops,
# and something that says whether it is running right now. Both describe
# the same week, so both are turned into the same weekly grid and every
# surface downstream stays unaware of which one this pool has.
CONF_FILTRATION_SCHEDULE_MODE: Final = "filtration_schedule_mode"
SCHEDULE_MODE_NONE: Final = "none"
SCHEDULE_MODE_HELPER: Final = "helper"
SCHEDULE_MODE_TIMES: Final = "times"
SCHEDULE_MODES: Final = [SCHEDULE_MODE_NONE, SCHEDULE_MODE_HELPER, SCHEDULE_MODE_TIMES]
CONF_FILTRATION_ON_TIME_ENTITY: Final = "filtration_on_time_entity"
CONF_FILTRATION_OFF_TIME_ENTITY: Final = "filtration_off_time_entity"
CONF_FILTRATION_STATE_ENTITY: Final = "filtration_state_entity"
SCHEDULE_TIME_KEYS: Final[tuple[str, ...]] = (
    CONF_FILTRATION_ON_TIME_ENTITY,
    CONF_FILTRATION_OFF_TIME_ENTITY,
    CONF_FILTRATION_STATE_ENTITY,
)
# Where a time can live. A `time` entity and an `input_datetime` are the
# native ways; a plain sensor is how many controllers expose theirs.
SCHEDULE_TIME_DOMAINS: Final[tuple[str, ...]] = ("time", "input_datetime", "sensor")
# What can answer "is the filtration running?" — an observation, not a control.
SCHEDULE_STATE_DOMAINS: Final[tuple[str, ...]] = (
    "binary_sensor",
    "switch",
    "input_boolean",
    "sensor",
)

# What a maintenance plan may ask for. Only equipment roles: the page sends a
# role, never an entity id, so the reach of a plan is exactly what the owner
# assigned to this pool. The filtration schedule is left out — a schedule
# is configuration, not an appliance, and has no on/off service.
MAINTENANCE_ROLES: Final[tuple[str, ...]] = tuple(
    role for role in EQUIPMENT_ROLES if role != ROLE_FILTRATION_SCHEDULE
)
# Domains we know how to command. A role pointed at a binary_sensor is an
# observation, not a control, so it is never offered.
MAINTENANCE_DOMAINS: Final[tuple[str, ...]] = (
    "switch",
    "input_boolean",
    "light",
    "fan",
    "climate",
    "water_heater",
    "cover",
)
# A pump runs or it does not; a cover opens or closes. Same idea, own words.
MAINTENANCE_ONOFF: Final[tuple[str, ...]] = ("on", "off")
MAINTENANCE_COVER: Final[tuple[str, ...]] = ("open", "closed")
# A window shorter than this is a mistake; longer than a day is not a visit.
MAINTENANCE_MIN_MINUTES: Final = 5
MAINTENANCE_MAX_MINUTES: Final = 1440

# Domains whose state is a way of saying on or off, rather than a measurement.
# Everything here answers "is it running?"; a sensor reporting 22.5 does not.
ONOFF_DOMAINS: Final[frozenset[str]] = frozenset(
    {
        "binary_sensor",
        "switch",
        "input_boolean",
        "light",
        "fan",
        "climate",
        "water_heater",
        "cover",
        "schedule",
        "humidifier",
    }
)
# Running equipment does not always say "on". A heat pump picked as a climate
# entity says "heat"; a water heater says "eco" or "performance"; a cover says
# "open". Chasing every mode Home Assistant may add is a losing game, so we
# name the handful of ways of being off and treat the rest as running.
OFF_STATES: Final[tuple[str, ...]] = ("off", "closed", "closing")
UNAVAILABLE_STATES: Final[tuple[str, ...]] = ("unknown", "unavailable")
# Equipment that aims for a temperature rather than merely running. These are
# the ones a tap must hand over to Home Assistant's own dialog: picking a mode
# and a target is not something a tile-sized switch can do.
THERMOSTAT_DOMAINS: Final[tuple[str, ...]] = ("climate", "water_heater")

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
CONF_CHEMISTRY_DAYS: Final = "chemistry_days"
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
DEFAULT_CHEMISTRY_DAYS: Final = 30
DEFAULT_REMINDER_TIME: Final = "10:00"

# Pool volume in m³ — enables the salt-dose hint and nothing else
CONF_POOL_VOLUME: Final = "pool_volume"

# Ideal water bands. pH and free chlorine are universal; the salt target
# depends on the chlorinator, so it is configurable.
CONF_SALT_TARGET_MIN: Final = "salt_target_min"
CONF_SALT_TARGET_MAX: Final = "salt_target_max"
DEFAULT_SALT_TARGET_MIN: Final = 2.5
DEFAULT_SALT_TARGET_MAX: Final = 4.5
IDEAL_PH: Final = (7.2, 7.6)
IDEAL_FREE_CHLORINE: Final = (1.0, 3.0)
IDEAL_TOTAL_ALKALINITY: Final = (80.0, 120.0)
IDEAL_CALCIUM_HARDNESS: Final = (200.0, 400.0)
# The right amount of stabilizer depends on how the chlorine gets there: a
# cell needs more of it than a floater, because the cell's chlorine is made
# in one spot and has the whole pool to survive.
IDEAL_CYANURIC: Final = (30.0, 50.0)
IDEAL_CYANURIC_SALT: Final = (60.0, 80.0)

# Combined chlorine (total minus free) is chloramine: the smell, the stinging
# eyes. Above this it is time to shock. The two readings only subtract into
# something meaningful when they came from the same test session.
COMBINED_CHLORINE_ALERT: Final = 0.5
COMBINED_CHLORINE_WINDOW_HOURS: Final = 6

# A schedule below the recommendation is only worth flagging once the gap
# is big enough to act on — rounding and a spare half hour are not news.
FILTRATION_SHORT_MIN_HOURS: Final = 1.0
FILTRATION_SHORT_FRACTION: Final = 0.2

# Filtration rule of thumb: hours per day ≈ water temperature / 2.
# Used only when the pool was not sized (see below).
FILTRATION_MIN_HOURS: Final = 2.0

# Sizing the filtration properly. All optional: with the flow rate and the
# volume we can do turnover maths instead of guessing, and with the cell
# output we can also check the chlorinator has time to make the day's
# chlorine. Missing any of it just falls back to the rule of thumb.
CONF_PUMP_FLOW: Final = "pump_flow"  # m³/h at full speed
CONF_PUMP_TYPE: Final = "pump_type"
CONF_CELL_OUTPUT: Final = "cell_output"  # g of chlorine per hour

PUMP_SINGLE_SPEED: Final = "single_speed"
PUMP_TWO_SPEED: Final = "two_speed"
PUMP_VARIABLE_SPEED: Final = "variable_speed"
PUMP_TYPES: Final = [PUMP_SINGLE_SPEED, PUMP_TWO_SPEED, PUMP_VARIABLE_SPEED]
LOW_SPEED_PUMPS: Final = (PUMP_TWO_SPEED, PUMP_VARIABLE_SPEED)
# Halving the speed roughly halves the flow, so the same turnover needs
# twice the hours — for roughly a quarter of the energy (power ~ rpm³).
LOW_SPEED_HOURS_FACTOR: Final = 2.0

# Turnovers per day, ramped between these water temperatures
TURNOVER_COOL_C: Final = 18.0
TURNOVER_WARM_C: Final = 28.0
TURNOVER_MIN: Final = 1.0
TURNOVER_MAX: Final = 2.0

# UV burns chlorine off, and it is the one thing about the weather the
# water temperature does not already carry. Applied to the chlorine demand
# only — it has nothing to say about how much water needs filtering.
CONF_UV_SOURCE: Final = "uv_source"
UV_REFERENCE: Final = 5.0  # the index the demand figures below assume
UV_PER_INDEX: Final = 0.06
UV_FACTOR_MIN: Final = 0.7
UV_FACTOR_MAX: Final = 1.4

# Chlorine demand in grams per m³ per day, ramped by water temperature
# (roughly 1 g/m³ = 1 ppm of free chlorine).
DEMAND_PER_DEGREE: Final = 0.1
DEMAND_OFFSET: Final = 1.0
DEMAND_MIN: Final = 0.5
DEMAND_MAX: Final = 3.0

# A closed cover means less debris and much less UV burn-off. Applied only
# while the cover entity actually reports closed.
COVER_HOURS_FACTOR: Final = 0.85
COVER_CHLORINE_FACTOR: Final = 0.6

# Filter pressure: a sensor beats a calendar. When one is linked and a clean
# baseline was captured, the filter wash alert follows the pressure rise
# instead of the fixed interval.
CONF_FILTER_PRESSURE_SOURCE: Final = "filter_pressure_source"
CONF_FILTER_PRESSURE_RISE: Final = "filter_pressure_rise"
DEFAULT_FILTER_PRESSURE_RISE: Final = 25  # percent over the clean baseline
# Below this the pump is almost certainly off, so the reading means nothing
MIN_MEANINGFUL_PRESSURE: Final = 0.1
METRIC_CLEAN_PRESSURE: Final = "filter_clean_pressure"
METRIC_CLEAN_PRESSURE_AT: Final = "filter_clean_pressure_at"
METRIC_PRESSURE_DUE: Final = "filter_pressure_due"

# Value keys (tracker "values" bucket)
KEY_PH: Final = "ph"
KEY_FREE_CHLORINE: Final = "free_chlorine"
KEY_TOTAL_CHLORINE: Final = "total_chlorine"
KEY_TOTAL_ALKALINITY: Final = "total_alkalinity"
KEY_CYANURIC_ACID: Final = "cyanuric_acid"
KEY_CALCIUM_HARDNESS: Final = "calcium_hardness"
KEY_WATER_TEMPERATURE: Final = "water_temperature"
KEY_SALT_LEVEL: Final = "salt_level"
KEY_SALT_ADDED: Final = "salt_added"
KEY_CHLORINATOR_OUTPUT: Final = "chlorinator_output"
KEY_CHLORINATOR_MODE: Final = "chlorinator_mode"
KEY_ACID_TANK_LEVEL: Final = "acid_tank_level"
# Derived, never declared: total minus free chlorine
KEY_COMBINED_CHLORINE: Final = "combined_chlorine"

# Timestamp keys (tracker "timestamps" bucket)
TS_WATER_TEST: Final = "water_test"
# The slow readings (stabilizer, hardness) — monthly, not every visit
TS_CHEMISTRY_TEST: Final = "chemistry_test"
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
# "empty" and "none" are real situations: a drum that ran dry, and a pool
# running without one at all (removed for maintenance, or never fitted).
ACID_TANK_LEVELS: Final = ["full", "three_quarters", "half", "quarter", "empty", "none"]
ACID_LEVEL_NONE: Final = "none"
# Levels worth telling somebody about. "none" is not one of them: there is
# nothing to refill, so nagging about it would be noise.
# "none" is not a refill problem — it is a pool whose pH is not being
# dosed at all, which is worth saying once in different words.
ACID_ALERT_LEVELS: Final = ("quarter", "empty", ACID_LEVEL_NONE)
CLEANING_TYPES: Final = ["vacuum", "waterline", "baskets"]

# Validation ranges: key -> (min, max, step)
NUMBER_RANGES: Final[dict[str, tuple[float, float, float]]] = {
    KEY_PH: (6.0, 9.0, 0.1),
    KEY_FREE_CHLORINE: (0.0, 10.0, 0.5),
    KEY_TOTAL_CHLORINE: (0.0, 10.0, 0.5),
    KEY_TOTAL_ALKALINITY: (0.0, 300.0, 10.0),
    KEY_CYANURIC_ACID: (0.0, 300.0, 5.0),
    KEY_CALCIUM_HARDNESS: (0.0, 1000.0, 10.0),
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
URL_KIOSK: Final = "/api/pool_maintenance_tracker/{token}/kiosk"
URL_MODE: Final = "/api/pool_maintenance_tracker/{token}/mode"
HISTORY_PERIODS: Final = (7, 30, 180)

TECHNICIAN_PERSON: Final = "technician"

# Re-notify damper for overdue reminders
RENOTIFY_DAYS: Final = 3


def schedule_mode(options: Mapping[str, Any]) -> str:
    """How this pool expresses its filtration schedule.

    Pools configured before there was a choice never stored one: a schedule
    helper is what they have, and the entity they already picked says so.
    """
    mode = options.get(CONF_FILTRATION_SCHEDULE_MODE)
    if mode in SCHEDULE_MODES:
        return mode
    if options.get(CONF_FILTRATION_SCHEDULE_ENTITY):
        return SCHEDULE_MODE_HELPER
    return SCHEDULE_MODE_NONE


def maintenance_values(domain: str) -> tuple[str, ...]:
    """The words a maintenance plan uses for a role in this domain."""
    return MAINTENANCE_COVER if domain == "cover" else MAINTENANCE_ONOFF


def equipment_on(domain: str, state: str) -> bool | None:
    """Whether this entity is running — ``None`` when that is not a question.

    The dashboards ask this of everything they are pointed at, including
    sensors that only ever report a number. ``None`` is the answer that says
    "this one is not an on/off thing", so a reading of 22.5 is never mistaken
    for equipment that happens not to be off.
    """
    if state in UNAVAILABLE_STATES:
        return None
    if domain not in ONOFF_DOMAINS and state not in ("on", "off", "open", "closed"):
        return None
    return state not in OFF_STATES


def signal_updated(entry_id: str) -> str:
    """Dispatcher signal fired when the tracker state for an entry changes."""
    return f"{DOMAIN}_{entry_id}_updated"


def signal_record(entry_id: str) -> str:
    """Dispatcher signal fired with each accepted maintenance record."""
    return f"{DOMAIN}_{entry_id}_record"
