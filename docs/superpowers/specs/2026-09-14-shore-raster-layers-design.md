# Shore Console raster layers — SST, chlorophyll, wave height — design

Written 2026-09-14. Scope: the one remaining piece of "wire up Shore Console" per
`docs/STATUS.md`'s phase 5 checklist — item 2, "MapLibre + deck.gl overlays for
SST, chlorophyll, wave height, and PFZ zones." PFZ and boundaries are already
done (an earlier round, GeoJSON overlays). This covers the three that are
gridded rasters and were explicitly deferred because no tile-serving
infrastructure existed at all.

Two decisions from brainstorming shape everything below:

- **Full dynamic TiTiler service**, not pre-rendered static images. Matches
  CLAUDE.md's stack table literally ("Tiles | TiTiler (raster) · pg_tileserv
  (vector)"). Chosen over the smaller pre-rendered-PNG alternative knowingly —
  this is real new infrastructure, not a config change.
- **COG generation is a manual script**, not a scheduled `arq` job. `arq` is in
  the locked stack table but is not wired anywhere in this codebase yet;
  standing it up for the first time would make this task also cover building a
  second subsystem. A script run before a demo is the honest scope for this
  round — layers do not self-refresh, and that is stated plainly rather than
  implied to be more automatic than it is.

## 1. Why a separate service, not a route on `api`

TiTiler needs GDAL/rasterio at the OS level — a materially heavier and
differently-shaped dependency footprint than the rest of the backend. This
session already hit one real outage from coupling `api`'s dependency set to
something it didn't originally need (the Docker image crash-looped on
`ModuleNotFoundError: No module named 'langgraph'` once `/advisory` made
`dhruva.app` import the full graph at module load time — see
`backend/Dockerfile`'s history). Bundling raster serving into the same
container repeats that mistake with a heavier dependency. A separate `titiler`
service keeps `api` exactly as lean as it needs to be for what it actually does,
and a crash in the tile server can't take the advisory endpoint down with it.

## 2. The TiTiler service

New top-level directory `titiler/` (sibling to `backend/`, `frontend/` — it is
its own deployable, not a Python subpackage of `dhruva`):

```
titiler/
  main.py       # TilerFactory + CORS, ~15 lines
  requirements.txt
  Dockerfile
```

```python
# titiler/main.py
from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from titiler.core.factory import TilerFactory
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers

app = FastAPI(title="dhruva-titiler")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

# Both router_prefix (on the factory) AND prefix (on include_router) are
# required — found by building and curling this service directly, not from
# the docs' minimal example, which showed neither. prefix alone mounts the
# routes correctly (/cog/tiles/... resolves) but the factory's own url_for(),
# which tilejson.json's self-referencing "tiles" field is built from, does
# not know about an externally-applied prefix — the first working build
# returned a tilejson whose own tile URL 404'd. TiTiler's own
# cogValidateExtension docs example is what showed both together.
cog = TilerFactory(router_prefix="/cog")
app.include_router(cog.router, prefix="/cog", tags=["Cloud Optimized GeoTIFF"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)


@app.get("/healthz")
def ping():
    return {"ping": "pong"}
```

This is TiTiler's own documented minimal pattern (`titiler.core.factory.TilerFactory`
+ CORS + exception handlers), not a custom reimplementation. `docker-compose.yml`
gets a new `titiler` service: builds from `./titiler`, mounts `./data/cogs:/data/cogs:ro`,
exposed on its own port, no dependency on `postgres`/`redis` since it only reads
files.

**Second finding, from the same build-and-curl pass:** the base image
(`ghcr.io/osgeo/gdal:ubuntu-small-3.9.2`) ships `numpy` via `apt`, which has no
pip `RECORD` file — `pip install -r requirements.txt` then refuses to upgrade
it for `rasterio`'s own numpy requirement ("Cannot uninstall numpy 1.26.4,
RECORD file not found"). Fixed with an isolated venv inside the image
(`python3 -m venv /opt/venv`, `ENV PATH="/opt/venv/bin:${PATH}"`) rather than
stacking `--ignore-installed` on top of `--break-system-packages` — the venv
sidesteps the apt/pip conflict entirely instead of forcing past it.

**Known, deliberately out-of-scope gap:** the tilejson response's own `tiles`
field is an absolute URL to whatever host TiTiler sees itself running on
(`http://localhost:8001/cog/tiles/...` in local dev) — MapLibre fetches actual
tile images directly from that URL, bypassing the `/tiles` Caddy/Vite proxy
entirely for every tile request after the first tilejson fetch. This works in
local dev (the browser can reach `localhost:8001` directly) but would not work
behind Caddy on Oracle A1, where only `:80`/`:443` are exposed and
`titiler:8000` is internal-network-only. Fixing this needs either a
reverse-proxy-aware TiTiler configuration (`X-Forwarded-Host` handling — some
titiler deployments support this, not investigated here) or client-side
rewriting of the tilejson response before handing it to MapLibre. Named here
rather than silently shipped as if solved, matching this project's own
convention for PFZ/thresholds/boundaries.

## 3. COG generation

**Corrected during spec self-review.** The original draft said this could
"reuse the existing Copernicus fetch path" wholesale. Checked directly rather
than assumed: `CopernicusAdapter.fetch()` (`backend/dhruva/sources/copernicus.py`)
is point-oriented — it takes one `lat, lon`, narrows to a small `tile_deg`-sized
box around that point, and returns a single reading. There is no existing call
that returns a `DEMO_BBOX`-sized grid in one shot. But its private
`_subset()` already calls `copernicusmarine.open_dataset(dataset_id=...,
variables=..., minimum_latitude=..., maximum_latitude=..., minimum_longitude=...,
maximum_longitude=..., start_datetime=..., end_datetime=...)` — genuinely
bbox-general, just always invoked with a small per-point tile today.

Rather than duplicate that kwarg-building logic in a second place, or reach
into another module's `_`-prefixed method from outside it, `_subset`'s core
"call `open_dataset` for this box" is extracted into a small **public**
function both call:

```python
# backend/dhruva/sources/copernicus.py — new, extracted from _subset's body
def fetch_grid(
    dataset_id: str, native_vars: list[str], *,
    lat_min: float, lat_max: float, lon_min: float, lon_max: float,
    start: dt.datetime, end: dt.datetime,
    username: str | None = None, password: str | None = None,
) -> xr.Dataset:
    """Blocking. Callers on the event loop must run this in a thread."""
    import copernicusmarine as cm
    kwargs: dict[str, object] = dict(
        dataset_id=dataset_id, variables=native_vars,
        minimum_latitude=lat_min, maximum_latitude=lat_max,
        minimum_longitude=lon_min, maximum_longitude=lon_max,
        start_datetime=start, end_datetime=end,
    )
    if username:
        kwargs["username"], kwargs["password"] = username, password
    return cm.open_dataset(**kwargs).load()
```

`CopernicusAdapter._subset()` becomes a thin wrapper calling `fetch_grid()` with
its existing small-tile bounds — no behaviour change there, verified by the
existing Copernicus tests continuing to pass unmodified.

`backend/dhruva/geo/generate_cogs.py`, run as `python -m dhruva.geo.generate_cogs`.
For each of the three variables (SST from `copernicus_phy_hourly`
/ `cmems_mod_glo_phy_anfc_0.083deg_PT1H-m`; wave height from `copernicus_wav`
/ `cmems_mod_glo_wav_anfc_0.083deg_PT3H-i`; chlorophyll from `copernicus_bgc_pft`
/ `cmems_mod_glo_bgc-pft_anfc_0.25deg_P1D-m` — confirmed via `Registry.load()`,
not guessed):

1. Look up the registry entry (`Registry.load("data/registry.yaml").by_id(...)`)
   to get the upstream `dataset_id` and native variable name — the same
   indirection `conditions_at()` already goes through, so a registry change
   does not need a matching code change here either.
2. Call `fetch_grid()` for `DEMO_BBOX` (`backend/dhruva/sources/cache.py`'s
   existing `(6.0, 24.0, 66.0, 94.0)`, reused directly, not redefined) and a
   short recent time window.
3. Select the single variable, collapse time (`.isel(time=-1)` or `.sel(...,
   method="nearest")`, matching `_read_point`'s own pattern) and depth where
   present (surface only, matching `_subset`'s existing `minimum_depth`/
   `maximum_depth` for `copernicus_phy_hourly`) down to a 2D `(lat, lon)`
   `DataArray`.
4. Write it as a Cloud-Optimized GeoTIFF via `rioxarray`:
   `da.rio.write_crs("EPSG:4326").rio.to_raster(path, driver="COG")`.
5. Write to `data/cogs/<variable>.tif` — already reachable inside `api` via the
   `DHRUVA_DATA_DIR` mount fixed earlier this session; `titiler` mounts the same
   host directory independently.

New dependency: `rioxarray`, added to `backend/pyproject.toml`'s existing `geo`
extra (it already carries `shapely`, `pyproj`, `geopandas` — the same family).

Output is a fixed set of three named files, not a versioned or timestamped
archive — regenerating overwrites in place. Simpler, and matches "a script you
re-run before a demo" rather than a pipeline with history to manage.

## 4. Proxy wiring

`deploy/Caddyfile` gets a `/tiles/*` block mirroring the existing `/api/*`
pattern exactly:

```
handle /tiles/* {
	uri strip_prefix /tiles
	reverse_proxy titiler:8000
}
```

`frontend/vite.config.ts`'s dev proxy gets the matching entry (`/tiles` →
`http://localhost:<titiler-port>`), so `fetch("/tiles/...")` from the frontend
works identically in dev (via Vite's proxy) and behind Caddy, the same
dev/deploy parity `/api` already has.

## 5. Frontend

`ShoreApp.tsx` gains three more `<Source type="raster">` / `<Layer type="raster">`
pairs, using TiTiler's `tilejson.json` endpoint as the source URL rather than a
hand-built `{z}/{x}/{y}` template — MapLibre reads bounds/minzoom/maxzoom
straight from the TileJSON response, which is less code and less to get wrong
than reconstructing that metadata by hand:

```
/tiles/cog/WebMercatorQuad/tilejson.json
  ?url=file:///data/cogs/sst.tif
  &rescale=18,33
  &colormap_name=thermal
```

Per-variable `rescale`/`colormap_name`, chosen as ordinary styling defaults
rather than asked about: SST 18–33 °C / `thermal`, chlorophyll 0–5 mg/m³ (log
distribution, most values cluster low) / `algae`, wave height 0–8 m (matches
the capsule's own 0–7.75 m saturating range) / `blues`.

These three layers toggle on the **already-present but currently decorative**
`SST` / `Chlorophyll` / `Wave Height` `LayerBtn`s in `ShoreApp.tsx` — the exact
`layersOn` state object already built for PFZ/boundaries in the earlier round
extends from two keys to five. No new UI pattern, the same one used twice
already.

## 6. Testing

- **`generate_cogs.py`**: a unit test against a small synthetic `xarray.DataArray`
  fixture (not a live Copernicus fetch) asserting the written file opens with
  `rasterio`, has the correct CRS, bounds within `DEMO_BBOX`, and exactly one
  band.
- **Orientation — found during implementation, not anticipated in this
  draft.** This project's own data-plane convention stores lat ascending
  (IMPLEMENTATION.md: "lat ascending, lon in -180..180"), but standard
  north-up GeoTIFF/COG readers — TiTiler included — require row 0 of the file
  to be the northernmost latitude. Verified empirically (write a known
  asymmetric pattern, read the bytes back) that writing an ascending-lat array
  through rioxarray as-is produces a file with south at the top: correctly
  georeferenced by coordinate, rendered upside down by any standard viewer.
  `write_cog` sorts lat descending before writing; a dedicated regression test
  pins the fix by asserting the affine transform's Y-resolution is negative.
- **`titiler` service**: not unit-tested — it's third-party code behind a ~15-line
  wrapper. Verified by a smoke test in the `compose` CI job (`curl` a known tile,
  assert 200 and a non-empty PNG), the same pattern already used for `/health`.
- **Frontend**: a pure test on the three tilejson URL strings (correct `rescale`/
  `colormap_name` per variable, correct `/tiles/...` prefix) — not a live tile
  fetch, matching how the PFZ/boundary layer tests were scoped.

## 7. Explicitly out of scope

- **Automatic refresh.** The script is manual. A stale demo layer is a known,
  stated limitation, not a hidden one — re-run `python -m dhruva.geo.generate_cogs`
  before a demo.
- **Any area outside `DEMO_BBOX`.** The tiles will show blank/transparent outside
  the Indian EEZ box, same scope boundary the capsule's own zone grid already has.
- **pg_tileserv / vector tiles.** PFZ and boundaries already render as GeoJSON,
  which was the deliberate choice in the earlier round precisely to avoid needing
  pg_tileserv. Not revisited here.
