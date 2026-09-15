"""Generate the three Shore Console raster layers as Cloud-Optimized GeoTIFFs.

Manual, not scheduled: re-run this before a demo to refresh the layers. No
arq job — arq is in the locked stack table but is not wired anywhere in this
codebase yet, and standing it up is out of scope for wiring three map layers.

Run: python -m dhruva.geo.generate_cogs
"""

from __future__ import annotations

import asyncio
import datetime as dt
import os
from pathlib import Path
from typing import TYPE_CHECKING

import rioxarray  # noqa: F401 — registers the .rio accessor on DataArray; not called directly

from dhruva.geo.rasters import write_manifest_entry
from dhruva.sources.cache import DEMO_BBOX, CacheKey, ZarrCache
from dhruva.sources.copernicus import fetch_grid
from dhruva.sources.registry import Registry

if TYPE_CHECKING:
    import xarray as xr

# codebook.py's own DHRUVA_DATA_DIR convention, reused rather than a second
# copy: inside the api container data/ is bind-mounted at a different depth
# than the local checkout, and this module lives at the same depth codebook.py
# does (backend/dhruva/<subpkg>/<file>.py, three parents below the repo root).
_DATA_DIR = Path(
    os.environ.get("DHRUVA_DATA_DIR", str(Path(__file__).resolve().parents[3] / "data"))
)
COG_DIR = _DATA_DIR / "cogs"

# (output filename, registry dataset id, canonical variable name, native var name)
_TARGETS = (
    ("sst.tif", "copernicus_phy_hourly", "sst", "thetao"),
    ("wave_height.tif", "copernicus_wav", "wave_height", "VHM0"),
    ("chlorophyll.tif", "copernicus_bgc_pft", "chlorophyll", "chl"),
)


def write_cog(da: xr.DataArray, path: Path) -> None:
    """A 2D (latitude, longitude) DataArray to a Cloud-Optimized GeoTIFF at path.

    Two things a naive rioxarray call gets wrong for this project's data, both
    found empirically rather than assumed:

    1. set_spatial_dims is required before write_crs: without it the CRS
       metadata silently does not attach to the right axes. The dimension
       names are `latitude`/`longitude`, not rioxarray's default x/y — and
       not the shortened `lat`/`lon` this file originally assumed either,
       which was a guess from registry.yaml's `lat_min`/`lon_min` KEY naming,
       not from the real data. copernicus.py's own point-selection code
       (`_nearest_wet`, `_read_point`) already reads Copernicus fields as
       `latitude`/`longitude` throughout; running this script live against
       real Copernicus data (not the synthetic test fixtures, which shared
       the same wrong assumption and so did not catch it) surfaced a
       `KeyError: 'lat'` that pinned the actual names down.
    2. This project's own data-plane convention (IMPLEMENTATION.md: "All of
       them normalise to: lat ascending...") stores latitude ascending —
       south to north. Standard north-up GeoTIFF/COG readers (TiTiler
       included) require the opposite: row 0 of the file must be the
       NORTHERNMOST latitude, i.e. latitude descending, giving a negative
       Y-resolution in the affine transform. Writing an ascending-latitude
       array as-is produces a file that is upside down: south at the top,
       north at the bottom. Sorting descending here, once, is cheaper than
       discovering an inverted SST layer during a demo.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    # Copernicus packs some variables (wave VHM0) as int16 with a 0.01 scale.
    # Keeping that encoding writes raw integers that TiTiler rescales as if they
    # were metres, so a 2.49 m sea renders as 249 and saturates the colour ramp.
    physical = da.astype("float32")
    physical.encoding = {}
    (
        physical.sortby("latitude", ascending=False)
        .rio.set_spatial_dims(x_dim="longitude", y_dim="latitude")
        .rio.write_crs("EPSG:4326")
        .rio.write_nodata(float("nan"))
        .rio.to_raster(str(path), driver="COG")
    )


async def _fetch_one(
    cache: ZarrCache, registry: Registry, entry_id: str, native_var: str
) -> xr.Dataset:
    """Cache-first: CacheKey.for_bbox takes the box in exactly DEMO_BBOX's own
    (lat_min, lat_max, lon_min, lon_max) shape, and ZarrCache is the same
    cache _subset()'s per-point path already writes to — reusing it here means
    a second script run within the TTL costs no network call, and keeps this
    script honouring the same cache the rest of the app does rather than
    working around it.
    """
    entry = registry.by_id(entry_id)
    when = dt.datetime.now(dt.UTC)
    key = CacheKey.for_bbox(entry.dataset_id, DEMO_BBOX, when, [native_var])

    cached = cache.get(key)
    if cached is not None:
        return cached

    depth_kwargs: dict[str, float] = {}
    if entry_id == "copernicus_phy_hourly":
        depth_kwargs = {"minimum_depth": 0.0, "maximum_depth": 1.0}
    ds = await asyncio.to_thread(
        fetch_grid,
        entry.dataset_id,
        [native_var],
        lat_min=key.lat_min,
        lat_max=key.lat_max,
        lon_min=key.lon_min,
        lon_max=key.lon_max,
        start=key.time_start,
        end=key.time_end,
        username=os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"),
        password=os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"),
        **depth_kwargs,
    )
    cache.put(key, ds)
    return ds


async def main() -> None:
    registry = Registry.load(os.environ.get("DHRUVA_REGISTRY", "data/registry.yaml"))
    cache = ZarrCache()
    for filename, entry_id, canonical_var, native_var in _TARGETS:
        ds = await _fetch_one(cache, registry, entry_id, native_var)
        da = ds[native_var]
        if "time" in da.dims:
            da = da.isel(time=-1)
        if "depth" in da.dims:
            da = da.isel(depth=0)
        write_cog(da, COG_DIR / filename)
        write_manifest_entry(
            canonical_var,
            {
                "file": filename,
                "dataset_id": registry.by_id(entry_id).dataset_id,
                "variable": native_var,
                "unit": da.attrs.get("units", ""),
                "valid_time": _valid_time(da),
                "generated_at": dt.datetime.now(dt.UTC).isoformat(),
            },
            COG_DIR,
        )
        print(f"wrote {COG_DIR / filename} for {canonical_var}")


def _valid_time(da: xr.DataArray) -> str | None:
    if "time" not in da.coords:
        return None
    import numpy as np

    return f"{np.datetime_as_string(da['time'].values, unit='s')}+00:00"


if __name__ == "__main__":
    asyncio.run(main())
