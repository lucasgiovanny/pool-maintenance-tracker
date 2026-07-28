"""The filtration advice: turnover, chlorination and the fallback."""

import pytest

from custom_components.pool_maintenance_tracker.filtration import (
    BASIS_CHLORINATION,
    BASIS_RULE_OF_THUMB,
    BASIS_TURNOVER,
    advise,
    chlorine_demand,
    turnovers_for,
)


def test_falls_back_to_the_rule_of_thumb():
    """With nothing configured, exactly what the integration always did."""
    advice = advise(27.4)
    assert advice.recommended_hours == 13.5
    assert advice.basis == BASIS_RULE_OF_THUMB
    assert advice.turnover_hours is None
    assert advice.chlorine_hours is None


def test_cold_water_still_gets_a_couple_of_hours():
    assert advise(3).recommended_hours == 2.0


def test_volume_alone_is_not_enough():
    """Turnover needs a flow rate; volume on its own cannot size anything."""
    assert advise(24, volume=48).basis == BASIS_RULE_OF_THUMB


def test_turnover_never_lowers_the_baseline():
    """A flow rate nobody can verify must not be able to under-filter.

    48 m³ at 9 m³/h works out at 8.5 h, but the rule of thumb asks for 12 —
    so 12 it is, and the turnover figure stays visible as the reasoning.
    """
    advice = advise(24, volume=48, flow=9)
    assert advice.recommended_hours == 12.0
    assert advice.basis == BASIS_RULE_OF_THUMB
    assert advice.turnover_hours == 8.5
    assert advice.rule_hours == 12.0


def test_turnover_raises_it_for_a_big_pool_on_a_weak_pump():
    """The case the rule of thumb gets dangerously wrong."""
    advice = advise(28, volume=80, flow=8)
    assert advice.basis == BASIS_TURNOVER
    assert advice.turnovers == 2.0
    assert advice.recommended_hours == 20.0  # the rule of thumb would say 14 h


@pytest.mark.parametrize(
    ("temperature", "turnovers"),
    [(10, 1.0), (18, 1.0), (23, 1.5), (28, 2.0), (35, 2.0)],
)
def test_turnovers_ramp_with_temperature(temperature, turnovers):
    assert turnovers_for(temperature) == turnovers


def test_chlorination_wins_when_the_cell_is_small():
    """A weak cell has to run longer than the turnover would ask."""
    # 30 °C -> 2 g/m³/day * 60 m³ = 120 g/day; a 6 g/h cell needs 20 h
    advice = advise(30, volume=60, flow=20, cell_output=6)
    assert advice.basis == BASIS_CHLORINATION
    assert advice.chlorine_hours == 20.0
    assert advice.turnover_hours == 6.0
    assert advice.recommended_hours == 20.0


def test_a_generous_cell_leaves_the_others_in_charge():
    advice = advise(30, volume=90, flow=9, cell_output=30)
    assert advice.basis == BASIS_TURNOVER
    assert advice.recommended_hours == 20.0


def test_uv_scales_the_chlorine_demand():
    """Two pools at the same temperature under different skies differ."""
    from custom_components.pool_maintenance_tracker.filtration import uv_factor

    assert uv_factor(None) == 1.0
    assert uv_factor(5) == 1.0  # the reference the demand figures assume
    assert uv_factor(0) == 0.7
    assert uv_factor(11) == pytest.approx(1.36)
    assert uv_factor(30) == 1.4  # clamped: no sky is that bad

    cloudy = advise(30, volume=60, flow=20, cell_output=6, uv=1)
    blazing = advise(30, volume=60, flow=20, cell_output=6, uv=10)
    assert blazing.chlorine_hours > cloudy.chlorine_hours
    assert blazing.basis == BASIS_CHLORINATION
    assert blazing.uv == 10


def test_chlorine_demand_is_clamped():
    assert chlorine_demand(5) == 0.5
    assert chlorine_demand(25) == 1.5
    assert chlorine_demand(50) == 3.0


def test_a_closed_cover_buys_time():
    uncovered = advise(28, volume=48, flow=9, cell_output=16)
    covered = advise(28, volume=48, flow=9, cell_output=16, covered=True)
    assert covered.recommended_hours < uncovered.recommended_hours
    assert covered.covered is True


def test_low_speed_alternative_only_for_pumps_that_have_one():
    assert advise(20, volume=48, flow=9).low_speed_hours is None
    advice = advise(20, volume=48, flow=9, pump_type="variable_speed")
    assert advice.recommended_hours == 10.0
    assert advice.low_speed_hours == 20.0


def test_nothing_ever_exceeds_a_full_day():
    advice = advise(30, volume=200, flow=4, pump_type="variable_speed")
    assert advice.recommended_hours == 24.0
    assert advice.low_speed_hours == 24.0
