"""Module registry and pool-type presets.

Single source of truth consumed by the config flow, entity platforms,
payload processor, page renderer, and reminder engine. Adding support for
new equipment means adding one ``PoolModule`` here plus entity descriptions
and page strings.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from .const import (
    CATEGORY_ACID_REFILL,
    CATEGORY_CELL_CLEAN,
    CATEGORY_CHLORINATOR,
    CATEGORY_CLEANING,
    CATEGORY_FILTER_WASH,
    CATEGORY_PROBE_CALIBRATION,
    CATEGORY_SALT,
    CATEGORY_WATER_TEST,
    CONF_CELL_DAYS,
    CONF_FILTER_DAYS,
    CONF_MODULES,
    CONF_PROBE_DAYS,
    DEFAULT_CELL_DAYS,
    DEFAULT_FILTER_DAYS,
    DEFAULT_PROBE_DAYS,
    KEY_ACID_TANK_LEVEL,
    KEY_CHLORINATOR_MODE,
    KEY_CHLORINATOR_OUTPUT,
    KEY_FREE_CHLORINE,
    KEY_PH,
    KEY_SALT_ADDED,
    KEY_SALT_LEVEL,
    POOL_TYPE_CHLORINE,
    POOL_TYPE_OTHER,
    POOL_TYPE_SALT,
    TS_ACID_REFILL,
    TS_ANY,
    TS_CELL_CLEAN,
    TS_CLEANING,
    TS_FILTER_WASH,
    TS_PROBE_CALIBRATION,
    TS_WATER_TEST,
)


@dataclass(frozen=True)
class ReminderSpec:
    """A periodic reminder tied to a timestamp key."""

    timestamp_key: str
    conf_key: str
    default_days: int


@dataclass(frozen=True)
class PoolModule:
    """A unit of optional pool equipment/functionality."""

    key: str
    tiles: tuple[str, ...]
    value_keys: tuple[str, ...] = ()
    timestamp_keys: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    reminder: ReminderSpec | None = None
    always_on: bool = False


MODULE_WATER_TESTING = PoolModule(
    key="water_testing",
    tiles=("water_test",),
    value_keys=(KEY_PH, KEY_FREE_CHLORINE),
    timestamp_keys=(TS_WATER_TEST,),
    categories=(CATEGORY_WATER_TEST,),
    always_on=True,
)

MODULE_SALT_CHLORINATOR = PoolModule(
    key="salt_chlorinator",
    tiles=("chlorinator", "salt", "cell_clean"),
    value_keys=(
        KEY_SALT_LEVEL,
        KEY_SALT_ADDED,
        KEY_CHLORINATOR_OUTPUT,
        KEY_CHLORINATOR_MODE,
    ),
    timestamp_keys=(TS_CELL_CLEAN,),
    categories=(CATEGORY_CHLORINATOR, CATEGORY_SALT, CATEGORY_CELL_CLEAN),
    reminder=ReminderSpec(TS_CELL_CLEAN, CONF_CELL_DAYS, DEFAULT_CELL_DAYS),
)

MODULE_ACID_TANK = PoolModule(
    key="acid_tank",
    tiles=("acid_refill",),
    value_keys=(KEY_ACID_TANK_LEVEL,),
    timestamp_keys=(TS_ACID_REFILL,),
    categories=(CATEGORY_ACID_REFILL,),
)

MODULE_FILTER = PoolModule(
    key="filter",
    tiles=("filter_wash",),
    timestamp_keys=(TS_FILTER_WASH,),
    categories=(CATEGORY_FILTER_WASH,),
    reminder=ReminderSpec(TS_FILTER_WASH, CONF_FILTER_DAYS, DEFAULT_FILTER_DAYS),
)

MODULE_PH_PROBE = PoolModule(
    key="ph_probe",
    tiles=("probe_calibration",),
    timestamp_keys=(TS_PROBE_CALIBRATION,),
    categories=(CATEGORY_PROBE_CALIBRATION,),
    reminder=ReminderSpec(TS_PROBE_CALIBRATION, CONF_PROBE_DAYS, DEFAULT_PROBE_DAYS),
)

MODULE_CLEANING = PoolModule(
    key="cleaning",
    tiles=("cleaning",),
    timestamp_keys=(TS_CLEANING,),
    categories=(CATEGORY_CLEANING,),
)

MODULE_CORE = PoolModule(
    key="core",
    tiles=(),
    timestamp_keys=(TS_ANY,),
    always_on=True,
)

MODULES: dict[str, PoolModule] = {
    module.key: module
    for module in (
        MODULE_WATER_TESTING,
        MODULE_SALT_CHLORINATOR,
        MODULE_ACID_TANK,
        MODULE_FILTER,
        MODULE_PH_PROBE,
        MODULE_CLEANING,
        MODULE_CORE,
    )
}

OPTIONAL_MODULE_KEYS: tuple[str, ...] = tuple(
    key for key, module in MODULES.items() if not module.always_on
)

POOL_TYPE_PRESETS: dict[str, tuple[str, ...]] = {
    POOL_TYPE_SALT: (
        MODULE_SALT_CHLORINATOR.key,
        MODULE_ACID_TANK.key,
        MODULE_FILTER.key,
        MODULE_PH_PROBE.key,
        MODULE_CLEANING.key,
    ),
    POOL_TYPE_CHLORINE: (MODULE_FILTER.key, MODULE_CLEANING.key),
    POOL_TYPE_OTHER: (MODULE_CLEANING.key,),
}

# Tile ids in the order they appear on the web page
TILE_ORDER: tuple[str, ...] = (
    "water_test",
    "chlorinator",
    "salt",
    "filter_wash",
    "cell_clean",
    "probe_calibration",
    "acid_refill",
    "cleaning",
)


def enabled_modules(options: Mapping[str, Any]) -> list[PoolModule]:
    """Return always-on modules plus the ones enabled in the entry options."""
    selected = set(options.get(CONF_MODULES, ()))
    return [module for module in MODULES.values() if module.always_on or module.key in selected]


def enabled_value_keys(options: Mapping[str, Any]) -> set[str]:
    return {key for module in enabled_modules(options) for key in module.value_keys}


def enabled_timestamp_keys(options: Mapping[str, Any]) -> set[str]:
    return {key for module in enabled_modules(options) for key in module.timestamp_keys}


def enabled_categories(options: Mapping[str, Any]) -> set[str]:
    return {cat for module in enabled_modules(options) for cat in module.categories}


def enabled_tiles(options: Mapping[str, Any]) -> list[str]:
    tiles = {tile for module in enabled_modules(options) for tile in module.tiles}
    return [tile for tile in TILE_ORDER if tile in tiles]


def enabled_reminders(options: Mapping[str, Any]) -> list[ReminderSpec]:
    return [module.reminder for module in enabled_modules(options) if module.reminder]


def timestamp_sensor_key(timestamp_key: str) -> str:
    """Entity key for the timestamp sensor tracking ``timestamp_key``."""
    return "last_maintenance" if timestamp_key == TS_ANY else f"last_{timestamp_key}"


def active_entity_keys(options: Mapping[str, Any]) -> set[str]:
    """All entity unique_id suffixes that should exist for the given options.

    Used to prune stale registry entries when modules are disabled.
    """
    keys: set[str] = {"last_record", "maintenance_logged", "access_qr"}
    keys.update(enabled_value_keys(options))
    for ts_key in enabled_timestamp_keys(options):
        keys.add(timestamp_sensor_key(ts_key))
    for reminder in enabled_reminders(options):
        keys.add(f"{reminder.timestamp_key}_due")
    return keys
