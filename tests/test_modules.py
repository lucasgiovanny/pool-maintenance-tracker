"""Tests for the module registry."""

from custom_components.pool_maintenance_tracker.const import (
    CONF_MODULES,
    POOL_TYPES,
)
from custom_components.pool_maintenance_tracker.modules import (
    MODULES,
    OPTIONAL_MODULE_KEYS,
    POOL_TYPE_PRESETS,
    TILE_ORDER,
    active_entity_keys,
    enabled_categories,
    enabled_tiles,
    enabled_value_keys,
)

from .conftest import CHLORINE_OPTIONS, SALT_OPTIONS


def test_presets_reference_known_modules():
    assert set(POOL_TYPE_PRESETS) == set(POOL_TYPES)
    for preset in POOL_TYPE_PRESETS.values():
        for key in preset:
            assert key in MODULES
            assert not MODULES[key].always_on


def test_all_tiles_are_ordered():
    tiles = {tile for module in MODULES.values() for tile in module.tiles}
    assert tiles == set(TILE_ORDER)


def test_optional_modules_excludes_always_on():
    assert "water_testing" not in OPTIONAL_MODULE_KEYS
    assert "core" not in OPTIONAL_MODULE_KEYS


def test_salt_pool_enables_everything():
    assert enabled_value_keys(SALT_OPTIONS) == {
        "ph",
        "free_chlorine",
        "total_chlorine",
        "total_alkalinity",
        "cyanuric_acid",
        "calcium_hardness",
        "water_temperature",
        "salt_level",
        "salt_added",
        "chlorinator_output",
        "chlorinator_mode",
        "acid_tank_level",
    }
    assert enabled_tiles(SALT_OPTIONS) == list(TILE_ORDER)


def test_chlorine_pool_is_reduced():
    keys = enabled_value_keys(CHLORINE_OPTIONS)
    assert keys == {"ph", "free_chlorine", "total_alkalinity", "water_temperature"}
    tiles = enabled_tiles(CHLORINE_OPTIONS)
    assert "chlorinator" not in tiles
    assert "acid_refill" not in tiles
    assert "water_test" in tiles
    categories = enabled_categories(CHLORINE_OPTIONS)
    assert "chlorinator" not in categories
    assert "filter_wash" in categories


def test_active_entity_keys_salt():
    keys = active_entity_keys(SALT_OPTIONS)
    assert "last_record" in keys
    assert "access_qr" in keys
    assert "maintenance_logged" in keys
    assert "last_maintenance" in keys
    assert "last_salt_added" in keys
    assert "chlorinator_mode" in keys
    assert "filter_wash_due" in keys
    assert "cell_clean_due" in keys
    assert "probe_calibration_due" in keys


def test_active_entity_keys_prune_on_disable():
    keys = active_entity_keys({CONF_MODULES: ["filter"]})
    assert "chlorinator_mode" not in keys
    assert "salt_level" not in keys
    assert "cell_clean_due" not in keys
    assert "filter_wash_due" in keys
