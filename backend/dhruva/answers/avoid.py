"""Query #8: "zones to avoid due to hazards or geofencing".

Warnings first, then lines: an active hazard always outranks a boundary. For
IMD, what is in force for the boat's sea (sources/imd_bulletin.live_status);
for boundaries, the three nearest distinct lines from Marine Regions, each
with its distance and the compass direction of its closest point. Every line
is indicative, never legal, and the answer says so.
"""

from __future__ import annotations

from typing import Any

from dhruva.answers import Answer, bearing_deg
from dhruva.evidence.schema import EvidenceItem

KIND = "avoid"
KM_PER_NM = 1.852


def _nm(value: float) -> float:
    return round(value) if value >= 10 else round(value, 1)


def _line_key(b: dict[str, Any]) -> tuple[str, str | None]:
    """The sentence for a line, and the neighbour it divides India from."""
    kind = (b.get("line_type") or "").lower()
    if "baseline" in kind:
        return "bnd_baseline", None
    if "200" in kind:
        return "bnd_eez", None
    others = [t for t in (b.get("territory1"), b.get("territory2")) if t and t != "India"]
    return "bnd_neighbour", (others[0] if others else None)


def compose(state: dict[str, Any]) -> Answer:
    lat, lon = state["lat"], state["lon"]
    a = Answer(kind=KIND, status="ok")

    # --- hazards -----------------------------------------------------------
    imd = state.get("imd") or {}
    src = state.get("cyclone_source")
    test_km = state.get("cyclone_distance_km") if src is None else None
    if src is not None:
        nm = _nm(src["distance_km"] / KM_PER_NM)
        a.add(
            "warning",
            "avoid_storm",
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
                cell_lat=src["lat"],
                cell_lon=src["lon"],
            )
        )
    elif test_km is not None:
        nm = _nm(test_km / KM_PER_NM)
        a.add("warning", "avoid_test_storm", distance=nm)
        a.evidence.append(
            EvidenceItem(
                key="storm_distance_nm", value=nm, unit="nm", dataset_id="risk_engine", cell="n/a"
            )
        )
    if imd.get("status") == "active" and src is None:
        a.add("warning", "avoid_imd_read")
    elif imd.get("status") == "none":
        a.add("warning", "avoid_no_imd")

    # --- lines -------------------------------------------------------------
    seen: set[tuple[str, str | None]] = set()
    shown = 0
    for b in state.get("boundaries") or []:
        key = _line_key(b)
        if key in seen or b.get("closest_lat") is None:
            continue
        seen.add(key)
        nm = _nm(float(b["distance_nm"]))
        values: dict[str, Any] = {
            "distance": nm,
            "bearing": {"bearing": bearing_deg(lat, lon, b["closest_lat"], b["closest_lon"])},
        }
        if key[1]:
            values["country"] = {"table": "countries", "word": key[1]}
        a.add("line", key[0], **values)
        a.evidence.append(
            EvidenceItem(
                key=f"boundary_{shown + 1}_nm",
                value=nm,
                unit="nm",
                dataset_id="marine_regions",
                upstream_dataset_id=b.get("name"),
                cell=f"{b['closest_lat']:.4f}N, {b['closest_lon']:.4f}E (closest point)",
                cell_lat=b["closest_lat"],
                cell_lon=b["closest_lon"],
            )
        )
        shown += 1
        if shown == 3:
            break
    if shown == 0:
        a.add("line", "bnd_unknown")
        if src is None and test_km is None and imd.get("status") != "active":
            a.status = "no_data"
    return a
