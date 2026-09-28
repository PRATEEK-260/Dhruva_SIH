"""Physical plausibility bounds for every reading, before it can reach a verdict.

A source can return a number that is well-formed and impossible: an SST of
2.6 °C in the Bay of Bengal (shown live by another SIH team's demo), a negative
wave height, a unit mix-up. Such a reading is dropped at the fetch layer and
recorded as an error, so the next source for that variable answers instead, and
if none does the variable is missing, which the rules read as UNKNOWN, never
SAFE.

These bound what is possible in Indian waters, not what is usual. SST in the
Bay of Bengal reaches 32-33 °C in a marine heatwave; a narrower "typical" band
would turn a real heatwave reading into "no data". They reject errors, not
extremes: an extreme reading is exactly what the verdict must see.
"""

from __future__ import annotations

from dhruva.sources.base import Observation
from dhruva.sources.registry import Variable

# (lowest, highest) plausible value, in the unit the registry delivers.
BOUNDS: dict[Variable, tuple[float, float]] = {
    Variable.SST: (15.0, 35.0),  # degC; Indian EEZ surface water
    Variable.WAVE_HEIGHT: (0.0, 20.0),  # m; significant wave height
    Variable.WAVE_PERIOD: (0.0, 30.0),  # s
    Variable.WIND_SPEED: (0.0, 150.0),  # kt; above the strongest cyclones recorded
    Variable.WIND_DIRECTION: (0.0, 360.0),  # degree
    Variable.CURRENT_SPEED: (0.0, 10.0),  # kt
    Variable.CURRENT_DIRECTION: (0.0, 360.0),  # degree
    Variable.CHLOROPHYLL: (0.0, 100.0),  # mg m-3
}


def implausible(obs: Observation) -> str | None:
    """Why this reading cannot be right, or None if it can."""
    value = obs.value
    if value != value:  # NaN
        return f"{obs.variable.value} is not a number"
    bounds = BOUNDS.get(obs.variable)
    if bounds is None:
        return None
    lo, hi = bounds
    if not lo <= value <= hi:
        return (
            f"implausible {obs.variable.value} {value:g} {obs.unit}, "
            f"outside {lo:g} to {hi:g}; reading dropped"
        )
    return None
