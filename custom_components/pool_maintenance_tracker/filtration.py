"""How long the filtration should run, and why.

Everything here is advice. The integration never drives the pump — these
numbers exist so whoever does can decide with something better than a guess.

Every input is optional. With the pool volume and the pump flow rate we can
do the real thing (turnover: how many times a day the whole pool passes
through the filter). On a salt pool with the cell output we can also check
the chlorinator has enough running time to make the chlorine the day burns.
With none of it we fall back to the usual rule of thumb, water temperature
divided by two, which is what the integration did before any of this
existed.

The result carries the reasoning, not just the number, so every surface can
show *why* and the reader can disagree with something concrete.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .const import (
    COVER_CHLORINE_FACTOR,
    COVER_HOURS_FACTOR,
    DEMAND_MAX,
    DEMAND_MIN,
    DEMAND_OFFSET,
    DEMAND_PER_DEGREE,
    FILTRATION_MIN_HOURS,
    LOW_SPEED_HOURS_FACTOR,
    LOW_SPEED_PUMPS,
    PUMP_SINGLE_SPEED,
    TURNOVER_COOL_C,
    TURNOVER_MAX,
    TURNOVER_MIN,
    TURNOVER_WARM_C,
)

BASIS_TURNOVER = "turnover"
BASIS_CHLORINATION = "chlorination"
BASIS_RULE_OF_THUMB = "rule_of_thumb"

MAX_HOURS = 24.0


@dataclass(frozen=True)
class FiltrationAdvice:
    """A recommendation and everything needed to justify it."""

    recommended_hours: float
    basis: str
    temperature: float
    turnovers: float | None = None
    volume: float | None = None
    flow: float | None = None
    cell_output: float | None = None
    turnover_hours: float | None = None
    chlorine_hours: float | None = None
    covered: bool = False
    low_speed_hours: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _round_half(hours: float) -> float:
    """Half-hour granularity — nobody sets a schedule to 13.7 hours."""
    return round(hours * 2) / 2


def turnovers_for(temperature: float) -> float:
    """Turnovers per day: warm water grows algae and burns chlorine faster."""
    if temperature <= TURNOVER_COOL_C:
        return TURNOVER_MIN
    if temperature >= TURNOVER_WARM_C:
        return TURNOVER_MAX
    span = TURNOVER_WARM_C - TURNOVER_COOL_C
    return TURNOVER_MIN + (TURNOVER_MAX - TURNOVER_MIN) * (temperature - TURNOVER_COOL_C) / span


def chlorine_demand(temperature: float) -> float:
    """Grams of chlorine consumed per m³ per day at this temperature."""
    demand = DEMAND_PER_DEGREE * temperature - DEMAND_OFFSET
    return min(DEMAND_MAX, max(DEMAND_MIN, demand))


def advise(
    temperature: float,
    *,
    volume: float | None = None,
    flow: float | None = None,
    cell_output: float | None = None,
    covered: bool = False,
    pump_type: str = PUMP_SINGLE_SPEED,
) -> FiltrationAdvice:
    """Recommended daily filtration hours for these conditions."""
    turnovers = turnovers_for(temperature)

    turnover_hours: float | None = None
    if volume and flow:
        turnover_hours = volume * turnovers / flow
        if covered:
            turnover_hours *= COVER_HOURS_FACTOR

    chlorine_hours: float | None = None
    if volume and cell_output:
        demand = chlorine_demand(temperature) * volume
        if covered:
            demand *= COVER_CHLORINE_FACTOR
        chlorine_hours = demand / cell_output

    candidates = [hours for hours in (turnover_hours, chlorine_hours) if hours is not None]
    if candidates:
        raw = max(candidates)
        # Whichever constraint is binding is the one worth explaining.
        basis = (
            BASIS_CHLORINATION
            if chlorine_hours is not None and raw == chlorine_hours
            else BASIS_TURNOVER
        )
    else:
        raw = temperature / 2
        if covered:
            raw *= COVER_HOURS_FACTOR
        basis = BASIS_RULE_OF_THUMB

    hours = min(MAX_HOURS, max(FILTRATION_MIN_HOURS, _round_half(raw)))

    # A pump with a low speed does the same turnover for a fraction of the
    # energy, as long as it runs longer.
    low_speed_hours = (
        min(MAX_HOURS, _round_half(hours * LOW_SPEED_HOURS_FACTOR))
        if pump_type in LOW_SPEED_PUMPS
        else None
    )

    return FiltrationAdvice(
        recommended_hours=hours,
        basis=basis,
        temperature=round(temperature, 1),
        turnovers=round(turnovers, 1),
        volume=volume,
        flow=flow,
        cell_output=cell_output,
        turnover_hours=None if turnover_hours is None else _round_half(turnover_hours),
        chlorine_hours=None if chlorine_hours is None else _round_half(chlorine_hours),
        covered=covered,
        low_speed_hours=low_speed_hours,
    )
