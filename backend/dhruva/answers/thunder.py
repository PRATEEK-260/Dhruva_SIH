"""Query #4: "lightning or cyclone alerts in my area".

Cyclone: what IMD has in force for the boat's sea (the same reading the
verdict uses). Lightning: there is no lightning feed, so this says what the
forecast says about thunderstorms over the next hours, labelled a forecast,
never observed lightning. A forecast thunderstorm makes the verdict CAUTION
(risk/rules.py, TSTORM-C1); observed lightning within 50 km would be NO-GO,
and nothing feeds that rule yet.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from dhruva.answers import Answer, bearing_deg, time_item
from dhruva.answers.avoid import KM_PER_NM, _nm
from dhruva.evidence.schema import EvidenceItem

KIND = "thunder"


def compose(state: dict[str, Any]) -> Answer:
    lat, lon = state["lat"], state["lon"]
    a = Answer(kind=KIND, status="ok")
    imd = state.get("imd") or {}
    src = state.get("cyclone_source")
    if src is not None:
        nm = _nm(src["distance_km"] / KM_PER_NM)
        a.add(
            "cyclone",
            "cyclone_in_force",
            category={"table": "categories", "word": src.get("category") or "Depression"},
            distance=nm,
            bearing={"bearing": bearing_deg(lat, lon, src["lat"], src["lon"])},
        )
        a.evidence.append(
            EvidenceItem(
                key="storm_distance_nm",
                value=nm,
                unit="nm",
                dataset_id="imd_rsmc_bulletin",
                upstream_dataset_id=src.get("title"),
                cell=f"{src['lat']:.1f}N, {src['lon']:.1f}E",
            )
        )
    elif imd.get("status") == "active":
        a.add("cyclone", "cyclone_read_bulletin")
    elif imd.get("status") == "none":
        a.add("cyclone", "cyclone_none")
    else:
        a.add("cyclone", "cyclone_unchecked")

    t = state.get("thunder")
    if t is None:
        a.add("thunder", "thunder_unchecked")
    elif t.get("from"):
        at = dt.datetime.fromisoformat(t["from"])
        a.add("thunder", "thunder_from", time=at)
        a.evidence.append(
            time_item(
                "thunderstorm_from",
                at,
                t["dataset_id"],
                f"{t['cell_lat']:.4f}N, {t['cell_lon']:.4f}E",
                cell_lat=t["cell_lat"],
                cell_lon=t["cell_lon"],
            )
        )
    else:
        from dhruva.sources.openmeteo_extra import THUNDER_HOURS

        a.add("thunder", "thunder_none", hours=THUNDER_HOURS)
        a.evidence.append(
            EvidenceItem(
                key="thunder_window_hours",
                value=THUNDER_HOURS,
                unit="h",
                dataset_id=t["dataset_id"],
                cell=f"{t['cell_lat']:.4f}N, {t['cell_lon']:.4f}E",
                is_forecast=True,
            )
        )
    return a
