"""How long the filtration should run, and why.

Everything here is advice. The integration never drives the pump — these
numbers exist so whoever does can decide with something better than a guess.

The rule of thumb — water temperature divided by two — is the baseline and
always applies. Everything else can only ask for *more* hours, never fewer:

- turnover (volume ÷ flow) catches the big pool on a weak pump, which the
  temperature rule would badly under-filter;
- on a salt pool, the cell needs enough running time to make the chlorine
  the day burns.

That ordering matters. A pump's nameplate flow is measured at a generous
point on its curve, and a real installation with a filter and pipework
delivers noticeably less — so a flow rate is a number the owner cannot
really verify. Letting it *lower* the recommendation would give an
unverifiable input the power to under-filter the pool. Letting it only
raise the recommendation makes overstating it harmless.

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
    UV_FACTOR_MAX,
    UV_FACTOR_MIN,
    UV_PER_INDEX,
    UV_REFERENCE,
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
    rule_hours: float | None = None
    covered: bool = False
    uv: float | None = None
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


def uv_factor(uv: float | None) -> float:
    """How much harder the sun is working than an average day.

    The water temperature already carries most of the weather — a pool at
    28 °C has been getting sun. UV is the part it does not carry: two pools
    at the same temperature under different skies burn chlorine at
    different rates.
    """
    if uv is None:
        return 1.0
    return min(UV_FACTOR_MAX, max(UV_FACTOR_MIN, 1 + (uv - UV_REFERENCE) * UV_PER_INDEX))


def chlorine_demand(temperature: float, uv: float | None = None) -> float:
    """Grams of chlorine consumed per m³ per day in these conditions."""
    demand = DEMAND_PER_DEGREE * temperature - DEMAND_OFFSET
    return min(DEMAND_MAX, max(DEMAND_MIN, demand)) * uv_factor(uv)


def advise(
    temperature: float,
    *,
    volume: float | None = None,
    flow: float | None = None,
    cell_output: float | None = None,
    covered: bool = False,
    uv: float | None = None,
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
        demand = chlorine_demand(temperature, uv) * volume
        if covered:
            demand *= COVER_CHLORINE_FACTOR
        chlorine_hours = demand / cell_output

    rule_hours = temperature / 2
    if covered:
        rule_hours *= COVER_HOURS_FACTOR

    # The baseline always applies; the rest can only ask for more.
    raw = max(hours for hours in (rule_hours, turnover_hours, chlorine_hours) if hours is not None)
    # Whichever constraint is binding is the one worth explaining.
    if chlorine_hours is not None and raw == chlorine_hours:
        basis = BASIS_CHLORINATION
    elif turnover_hours is not None and raw == turnover_hours:
        basis = BASIS_TURNOVER
    else:
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
        rule_hours=_round_half(rule_hours),
        covered=covered,
        uv=uv,
        low_speed_hours=low_speed_hours,
    )
