"""Query #5: "regions with high chlorophyll and favourable SST".

Today's satellite chlorophyll (GlobColour L4 gap-free) and sea temperature
(OSTIA) over a box of about 120 x 120 km around the boat. "High" is relative
and stated: the top quarter of chlorophyll in that box today, so no absolute
threshold is invented. "Favourable" sea temperature uses FAVOURABLE_SST_C,
which has no published source in hand and is marked PROVISIONAL everywhere it
shows. The answer gives the nearest cell meeting both, next to the INCOIS
zone for comparison: INCOIS's PFZ is the official advisory; this is not.

Under NO-GO it suggests nothing (NO-GO outranks any zone).
"""

from __future__ import annotations

from typing import Any

from dhruva.answers import Answer, bearing_deg, distance_km
from dhruva.evidence.schema import EvidenceItem

KIND = "productive"
# PROVISIONAL: a working range for tropical pelagic fishing grounds, not an
# INCOIS or published criterion. Replace with a cited range before any claim.
FAVOURABLE_SST_C = (26.0, 30.0)
PROVISIONAL = True
TOP_FRACTION = 0.25
HALF_BOX_DEG = 0.55


def compose(state: dict[str, Any], no_go: bool) -> Answer:
    lat, lon = state["lat"], state["lon"]
    p = state.get("productive")
    if no_go:
        a = Answer(kind=KIND, status="ok")
        a.add("productive", "productive_no_go")
        return a
    if p is None:
        a = Answer(kind=KIND, status="no_data")
        a.add("productive", "productive_no_data")
        return a
    a = Answer(kind=KIND, status="ok")
    cell = p.get("cell")
    if cell is None:
        a.add("productive", "productive_none", low=FAVOURABLE_SST_C[0], high=FAVOURABLE_SST_C[1])
    else:
        nm = round(distance_km(lat, lon, cell["lat"], cell["lon"]) / 1.852)
        values = {
            "distance": nm,
            "bearing": {"bearing": bearing_deg(lat, lon, cell["lat"], cell["lon"])},
            "chl": round(cell["chl"], 2),
            "sst": round(cell["sst"], 1),
        }
        a.add("productive", "productive_here" if nm < 2 else "productive_at", **values)
        where = f"{cell['lat']:.3f}N, {cell['lon']:.3f}E"
        a.evidence += [
            EvidenceItem(
                key="productive_distance_nm",
                value=nm,
                unit="nm",
                dataset_id="copernicus_globcolour_nrt",
                cell=where,
                cell_lat=cell["lat"],
                cell_lon=cell["lon"],
            ),
            EvidenceItem(
                key="productive_chl",
                value=cell["chl"],
                unit="mg m-3",
                dataset_id="copernicus_globcolour_nrt",
                upstream_dataset_id=p["chl_dataset"],
                cell=where,
                threshold=p["chl_p75"],
                rule_id="TOP-QUARTER",
            ),
            EvidenceItem(
                key="productive_sst",
                value=cell["sst"],
                unit="degC",
                dataset_id="copernicus_ostia_nrt",
                upstream_dataset_id=p["sst_dataset"],
                cell=where,
            ),
        ]
    pfz = state.get("pfz")
    if pfz is not None:
        pnm = round(float(pfz["distance_nm"]))
        a.add("compare", "compare_pfz", distance=pnm, bearing={"bearing": pfz["bearing_deg"]})
    else:
        a.add("compare", "compare_no_pfz")
    a.evidence.append(
        EvidenceItem(
            key="favourable_sst_low",
            value=FAVOURABLE_SST_C[0],
            unit="degC",
            dataset_id="provisional_range",
            cell="n/a",
        )
    )
    a.evidence.append(
        EvidenceItem(
            key="favourable_sst_high",
            value=FAVOURABLE_SST_C[1],
            unit="degC",
            dataset_id="provisional_range",
            cell="n/a",
        )
    )
    return a


def pick(chl: Any, sst: Any, lat: float, lon: float) -> dict[str, Any] | None:
    """The nearest cell in the top quarter of chlorophyll whose sea temperature
    is in the favourable range. Inputs are 2-D arrays on one grid (lat x lon)
    with their coordinate vectors; NaN is land or cloud and never qualifies."""
    import numpy as np

    c, s = np.asarray(chl["values"], float), np.asarray(sst["values"], float)
    lats, lons = np.asarray(chl["lat"], float), np.asarray(chl["lon"], float)
    finite = np.isfinite(c) & np.isfinite(s)
    if not finite.any():
        return None
    p75 = float(np.quantile(c[finite], 1 - TOP_FRACTION))
    ok = finite & (c >= p75) & (s >= FAVOURABLE_SST_C[0]) & (s <= FAVOURABLE_SST_C[1])
    out: dict[str, Any] = {"chl_p75": p75, "cell": None}
    if not ok.any():
        return out
    glat, glon = np.meshgrid(lats, lons, indexing="ij")
    d = np.where(ok, (glat - lat) ** 2 + ((glon - lon) * np.cos(np.radians(lat))) ** 2, np.inf)
    i, j = np.unravel_index(int(np.argmin(d)), d.shape)
    out["cell"] = {
        "lat": float(lats[i]),
        "lon": float(lons[j]),
        "chl": float(c[i, j]),
        "sst": float(s[i, j]),
    }
    return out


CHL_DATASET = "cmems_obs-oc_glo_bgc-plankton_nrt_l4-gapfree-multi-4km_P1D"
SST_DATASET = "METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2"
_CACHE: dict[tuple[Any, ...], dict[str, Any] | None] = {}


def _fetch_sync(lat: float, lon: float, day: Any, username: Any, password: Any) -> dict[str, Any]:
    """Blocking. The newest day each product has within the last 5 days, over
    the box; SST is put on the chlorophyll grid by nearest neighbour."""
    import datetime as dt

    import numpy as np

    from dhruva.sources.copernicus import fetch_grid

    box = dict(
        lat_min=lat - HALF_BOX_DEG,
        lat_max=lat + HALF_BOX_DEG,
        lon_min=lon - HALF_BOX_DEG,
        lon_max=lon + HALF_BOX_DEG,
    )
    start = dt.datetime.combine(day - dt.timedelta(days=5), dt.time())
    end = dt.datetime.combine(day, dt.time(23, 59))
    chl = fetch_grid(
        CHL_DATASET, ["CHL"], start=start, end=end, username=username, password=password, **box
    )
    sst = fetch_grid(
        SST_DATASET,
        ["analysed_sst"],
        start=start,
        end=end,
        username=username,
        password=password,
        **box,
    )

    def newest(da: Any) -> Any:
        for k in range(da.sizes["time"] - 1, -1, -1):
            if np.isfinite(da.isel(time=k).values).any():
                return da.isel(time=k)
        return None

    c, s = newest(chl["CHL"]), newest(sst["analysed_sst"])
    if c is None or s is None:
        return {"cell": None, "empty": True}
    # Nearest SST cell for each chlorophyll cell; .sel needs no scipy, unlike .interp.
    s_on_c = (
        s.sel(latitude=c["latitude"].values, longitude=c["longitude"].values, method="nearest")
        - 273.15
    )
    picked = pick(
        {"values": c.values, "lat": c["latitude"].values, "lon": c["longitude"].values},
        {"values": s_on_c.values},
        lat,
        lon,
    )
    if picked is None:
        return {"cell": None, "empty": True}
    return {
        **picked,
        "chl_dataset": f"{CHL_DATASET} {str(c['time'].values)[:10]}",
        "sst_dataset": f"{SST_DATASET} {str(s['time'].values)[:10]}",
    }


async def fetch(lat: float, lon: float, when: Any, *, username: Any, password: Any) -> Any:
    """None when the satellite fetch failed or the box had no clear water."""
    import asyncio

    key = (round(lat, 2), round(lon, 2), when.date())
    if key in _CACHE:
        return _CACHE[key]
    try:
        got = await asyncio.to_thread(_fetch_sync, lat, lon, when.date(), username, password)
    except Exception:
        return None
    result = None if got.get("empty") else got
    _CACHE[key] = result
    return result
