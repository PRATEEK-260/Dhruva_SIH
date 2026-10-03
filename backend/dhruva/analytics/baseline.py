"""The fetch half of query #7: box means for the current window and the same
window in earlier years.

dhruva.analytics.decline does the arithmetic and picks the sentences; this
module only turns a gridded dataset into one WindowMean per year. Each source
is fetched once, for the whole span from the oldest window to the newest, and
the windows are cut from that one grid: one Copernicus call per variable rather
than one per year.

Days with no finite value anywhere in the box (cloud over the box, for ocean
colour) are not days of data; a window with none at all has mean None, which
decline.compare() reads as a missing year, never as zero.
"""

from __future__ import annotations

import asyncio
import datetime as dt
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from dhruva.analytics.decline import (
    WINDOW_DAYS,
    WindowMean,
    box_around,
    compare,
    windows,
)
from dhruva.sources.base import FetchError
from dhruva.sources.registry import Variable

if TYPE_CHECKING:
    import xarray as xr


@dataclass(frozen=True, slots=True)
class BaselineSource:
    """Where one variable's windows come from."""

    variable: Variable
    dataset_id: str  # DHRUVA's name for it, shown on the evidence card
    upstream: str  # the Copernicus dataset_id
    native: str  # the variable inside it
    unit: str  # canonical unit after `offset`
    offset: float = 0.0  # added to the native value (Kelvin to Celsius: -273.15)
    latency_days: int = 1  # the newest day the product reliably has, before `when`
    years_back: int = 10
    depth: bool = False  # the variable has a depth axis; read the surface level
    # A separate product for the baseline years, when the current one does not
    # reach back far enough. None: one product for every window.
    baseline_dataset_id: str | None = None
    baseline_upstream: str | None = None


def window_means(
    ds: xr.Dataset, source: BaselineSource, wins: list[tuple[int, dt.date, dt.date]]
) -> list[WindowMean]:
    """One WindowMean per window, from a grid already cut to the box.

    The mean is over every finite cell of every day in the window, so a day
    half-covered by cloud still contributes what it has. `days` counts the
    days with at least one finite cell.
    """
    import numpy as np

    field = ds[source.native]
    if source.depth and "depth" in field.dims:
        field = field.isel(depth=0)
    out: list[WindowMean] = []
    for year, start, end in wins:
        sel = field.sel(
            time=slice(np.datetime64(start), np.datetime64(end) + np.timedelta64(1, "D"))
        )
        # Drop a stamp that lands exactly on the next midnight.
        sel = sel.where(sel["time"] < np.datetime64(end + dt.timedelta(days=1)), drop=True)
        values = np.asarray(sel.values, dtype="float64")
        if values.size == 0:
            out.append(WindowMean(year, start, end, None, 0))
            continue
        finite = np.isfinite(values)
        flat = values.reshape(values.shape[0], -1) if values.ndim > 1 else values[:, None]
        days = int(np.isfinite(flat).any(axis=1).sum())
        if not finite.any():
            out.append(WindowMean(year, start, end, None, 0))
            continue
        out.append(WindowMean(year, start, end, float(values[finite].mean()) + source.offset, days))
    return out


# Window means already worked out, keyed on the product, the box and the
# windows. A box is fixed by its centre, and every window by the current one's
# end date, so a repeat question that day costs nothing. In process only.
_CACHE: dict[tuple[Any, ...], list[WindowMean]] = {}
_CACHE_MAX = 64


def _fetch(
    source: BaselineSource,
    upstream: str,
    box: tuple[float, float, float, float],
    start: dt.date,
    end: dt.date,
    username: str | None,
    password: str | None,
) -> xr.Dataset:
    """Blocking. Runs in a worker thread."""
    from dhruva.sources.copernicus import fetch_grid

    lat_min, lat_max, lon_min, lon_max = box
    extra: dict[str, float] = {"minimum_depth": 0.0, "maximum_depth": 1.0} if source.depth else {}
    return fetch_grid(
        upstream,
        [source.native],
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        start=dt.datetime.combine(start, dt.time()),
        end=dt.datetime.combine(end, dt.time(23, 59)),
        username=username,
        password=password,
        **extra,
    )


async def source_change(
    source: BaselineSource,
    lat: float,
    lon: float,
    when: dt.datetime,
    *,
    username: str | None,
    password: str | None,
) -> tuple[Any, list[FetchError]]:
    """The Change for one variable, or None with the reason recorded.

    With one product, one call covers every window. With a separate baseline
    product, the current window and the baseline span are two calls, in
    parallel.
    """
    box = box_around(lat, lon)
    end = when.astimezone(dt.UTC).date() - dt.timedelta(days=source.latency_days)
    wins = windows(end, source.years_back)

    async def means_for(upstream: str, part: list[tuple[int, dt.date, dt.date]]):
        key = (upstream, source.native, round(lat, 2), round(lon, 2), part[0][2], len(part))
        if key in _CACHE:
            return _CACHE[key]
        ds = await asyncio.to_thread(
            _fetch, source, upstream, box, part[-1][1], part[0][2], username, password
        )
        try:
            got = window_means(ds, source, part)
        finally:
            ds.close()
        if len(_CACHE) >= _CACHE_MAX:
            _CACHE.pop(next(iter(_CACHE)))
        _CACHE[key] = got
        return got

    try:
        if source.baseline_upstream is None:
            means = await means_for(source.upstream, wins)
        else:
            current, base = await asyncio.gather(
                means_for(source.upstream, wins[:1]),
                means_for(source.baseline_upstream, wins[1:]),
            )
            means = current + base
    except Exception as exc:  # a failed source is No data, never a crash
        return None, [
            FetchError(
                dataset_id=source.dataset_id,
                variable=source.variable,
                error=f"{type(exc).__name__}: {exc}",
            )
        ]
    change = compare(
        source.variable,
        source.unit,
        means[0],
        means[1:],
        dataset_id=source.dataset_id,
        upstream_dataset_id=source.upstream,
        baseline_dataset_id=source.baseline_dataset_id,
        baseline_upstream_dataset_id=source.baseline_upstream,
    )
    errors = []
    if change is None:
        have = sum(1 for m in means[1:] if m.mean is not None)
        errors.append(
            FetchError(
                dataset_id=source.dataset_id,
                variable=source.variable,
                error=(
                    f"no data for the current {WINDOW_DAYS} days"
                    if means[0].mean is None
                    else f"only {have} baseline year(s) with data"
                ),
            )
        )
    return change, errors


# Chosen by measurement on 2026-10-03, for a 20 km box at 11.05N 79.95E:
#
# Chlorophyll: the multi-year GlobColour L4 gap-free product runs from
# 1997-09-04 to 8 days before today (its interim extension), so it serves the
# current window AND the baseline: one product, no cross-product bias. The NRT
# product keeps only the last 17 days and cannot. 10 years in one call: 11 s.
# Gap-free (cloud-filled) is the L4 product's own interpolation, not ours.
#
# SST: OSTIA (Met Office L4). The reprocessed record runs 1981 to 2026-03-31,
# so it serves the baseline years; the NRT product (from 2024-01-17, 1 day
# behind) serves the current window. Where both cover the window (2024, 2025)
# NRT read 0.04-0.06 C warmer than REP: below the 0.1 C the answer speaks.
# 7 s per call.
SOURCES: tuple[BaselineSource, ...] = (
    BaselineSource(
        variable=Variable.CHLOROPHYLL,
        dataset_id="copernicus_globcolour_my",
        upstream="cmems_obs-oc_glo_bgc-plankton_my_l4-gapfree-multi-4km_P1D",
        native="CHL",
        unit="mg m-3",
        latency_days=8,
    ),
    BaselineSource(
        variable=Variable.SST,
        dataset_id="copernicus_ostia_nrt",
        upstream="METOFFICE-GLO-SST-L4-NRT-OBS-SST-V2",
        native="analysed_sst",
        unit="degC",
        offset=-273.15,
        latency_days=1,
        baseline_dataset_id="copernicus_ostia_rep",
        baseline_upstream="METOFFICE-GLO-SST-L4-REP-OBS-SST",
    ),
)


async def decline_changes(
    lat: float,
    lon: float,
    when: dt.datetime,
    *,
    username: str | None,
    password: str | None,
    sources: tuple[BaselineSource, ...] | None = None,
) -> tuple[dict[str, Any], list[FetchError]]:
    """Chlorophyll and SST windows, fetched in parallel. The result is what the
    graph's `decline` key holds: a Change or None per variable, and the box."""
    chosen = SOURCES if sources is None else sources
    results = await asyncio.gather(
        *(source_change(s, lat, lon, when, username=username, password=password) for s in chosen)
    )
    out: dict[str, Any] = {"chlorophyll": None, "sst": None, "box": box_around(lat, lon)}
    errors: list[FetchError] = []
    for source, (change, errs) in zip(chosen, results, strict=True):
        out[source.variable.value] = change
        errors.extend(errs)
    return out, errors
