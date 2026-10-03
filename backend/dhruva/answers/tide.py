"""Query #3's missing part: tides. The next high and low water from Open-Meteo's
marine model, at the boat's position. A model estimate, not for navigation,
as Open-Meteo itself warns; the caveat says so every time."""

from __future__ import annotations

import datetime as dt
from typing import Any

from dhruva.answers import Answer, time_item

KIND = "tide"


def compose(state: dict[str, Any]) -> Answer:
    t = state.get("tide")
    if t is None:
        a = Answer(kind=KIND, status="no_data")
        a.add("tide", "tide_no_data")
        return a
    a = Answer(kind=KIND, status="ok")
    high = dt.datetime.fromisoformat(t["high"]["at"])
    low = dt.datetime.fromisoformat(t["low"]["at"])
    key = "tide_high_first" if high < low else "tide_low_first"
    a.add("tide", key, high=high, low=low)
    cell = f"{t['cell_lat']:.4f}N, {t['cell_lon']:.4f}E"
    for name, at in (("high_water", high), ("low_water", low)):
        a.evidence.append(
            time_item(
                name, at, t["dataset_id"], cell, cell_lat=t["cell_lat"], cell_lon=t["cell_lon"]
            )
        )
    return a
