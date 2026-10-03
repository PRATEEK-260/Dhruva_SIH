"""Query #6: "safest route considering weather and sea state".

Not a route planner: a straight-line check from the boat to the nearest fresh
INCOIS fishing zone. Wave height is read at points along the line; if any
exceeds the boat's caution limit, or the line passes within the cyclone
radius of IMD's centre, no route is suggested and the answer says why. The
line is drawn as a reference, never as navigation. An A* search over a cost
grid is future work.
"""

from __future__ import annotations

from typing import Any

from dhruva.answers import Answer, bearing_deg, distance_km
from dhruva.evidence.schema import EvidenceItem
from dhruva.risk.thresholds import CYCLONE_RADIUS_KM, thresholds_for

KIND = "route"
SAMPLES = 8


def line_points(lat: float, lon: float, lat2: float, lon2: float) -> list[tuple[float, float]]:
    """Evenly spaced points from the boat to the target, both ends included.
    Linear in lon/lat: over tens of miles the difference from a great circle
    is far smaller than the wave model's grid."""
    return [
        (lat + (lat2 - lat) * i / (SAMPLES - 1), lon + (lon2 - lon) * i / (SAMPLES - 1))
        for i in range(SAMPLES)
    ]


def compose(state: dict[str, Any], no_go: bool) -> Answer:
    lat, lon = state["lat"], state["lon"]
    pfz = state.get("pfz")
    if no_go:
        a = Answer(kind=KIND, status="ok")
        a.add("route", "route_no_go")
        return a
    if pfz is None:
        a = Answer(kind=KIND, status="no_data")
        a.add("route", "route_no_target")
        return a
    r = state.get("route_check")
    if r is None or not r.get("waves") or any(w is None for w in r["waves"]):
        a = Answer(kind=KIND, status="no_data")
        a.add("route", "route_unchecked")
        return a

    a = Answer(kind=KIND, status="ok")
    tlat, tlon = pfz["lat"], pfz["lon"]
    nm = round(distance_km(lat, lon, tlat, tlon) / 1.852)
    worst = max(r["waves"])
    from dhruva.graph.state import BoatClass

    limit = thresholds_for(state.get("boat_class") or BoatClass.FRP_UNDER_12M).caution_wave_m
    bearing = {"bearing": bearing_deg(lat, lon, tlat, tlon)}
    src = state.get("cyclone_source")
    near_storm = src is not None and any(
        distance_km(p[0], p[1], src["lat"], src["lon"]) <= CYCLONE_RADIUS_KM for p in r["points"]
    )
    if near_storm:
        a.add("route", "route_storm", distance=nm, bearing=bearing)
    elif worst >= limit:
        a.add("route", "route_rough", distance=nm, bearing=bearing, wave=worst, limit=limit)
    else:
        a.add("route", "route_ok", distance=nm, bearing=bearing, wave=worst, limit=limit)
        a.extra["line"] = [[lon, lat], [tlon, tlat]]
    a.evidence += [
        EvidenceItem(
            key="route_distance_nm",
            value=nm,
            unit="nm",
            dataset_id="incois_pfz",
            upstream_dataset_id=f"straight line to PFZ_Automation:pfzlines {pfz.get('uid')}",
            cell=f"{tlat:.4f}N, {tlon:.4f}E",
        ),
        EvidenceItem(
            key="route_max_wave",
            value=worst,
            unit="m",
            dataset_id="open_meteo_marine",
            upstream_dataset_id=f"wave height at {len(r['points'])} points along the line",
            cell="along the line",
            is_forecast=True,
            threshold=limit,
            rule_id="WAVE-C2",
        ),
    ]
    return a
