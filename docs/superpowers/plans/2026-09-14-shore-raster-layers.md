# Shore Console Raster Layers Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Shore Console renders real SST, chlorophyll and wave-height map layers, the last piece of "wire up Shore Console" per `docs/STATUS.md`.

**Architecture:** A new, separate `titiler` service (kept out of the lean `api` container) serves tiles from Cloud-Optimized GeoTIFFs. A manually-run script generates those COGs from real Copernicus data for the fixed demo bounding box. Caddy and the Vite dev proxy both gain a `/tiles/*` route matching the existing `/api/*` pattern. Three new raster layers in `ShoreApp.tsx` reuse the toggle pattern already built for PFZ/boundaries.

**Tech Stack:** TiTiler (`titiler.core`) · rioxarray · the existing `copernicusmarine` toolbox · MapLibre raster sources

**Spec:** `docs/superpowers/specs/2026-09-14-shore-raster-layers-design.md`

## Global Constraints

- `titiler` is its own service, never merged into `api`'s Dockerfile or dependency set — `api`'s crash-loop earlier this session (a heavy dependency pulled in at module-import time) is exactly the failure mode this avoids.
- COG generation is a manual script. No scheduled job, no `arq` (not wired anywhere in this codebase yet — standing it up is out of scope here).
- `DEMO_BBOX = (6.0, 24.0, 66.0, 94.0)` (`backend/dhruva/sources/cache.py`) is reused directly, never redefined.
- `_subset()`'s existing behavior must not change — the refactor in Task 1 is behavior-preserving, proven by a test, not just asserted.
- No live network calls in automated tests — `copernicusmarine.open_dataset` is mocked at the boundary, matching how the rest of this codebase already tests Copernicus-adjacent code (no existing test hits it live).
- Commits: `area: imperative summary`, no AI co-author trailer (project convention, confirmed via `git log` on every commit in this repo).

---

## File Structure

**Create:**
- `titiler/main.py`, `titiler/requirements.txt`, `titiler/Dockerfile`
- `backend/dhruva/geo/generate_cogs.py`
- `backend/tests/test_generate_cogs.py`
- `backend/tests/test_copernicus_fetch_grid.py`

**Modify:**
- `backend/dhruva/sources/copernicus.py` — extract `fetch_grid()`, `_subset()` becomes a thin wrapper
- `backend/pyproject.toml` — add `rioxarray` to the `geo` extra
- `docker-compose.yml` — add the `titiler` service
- `deploy/Caddyfile` — add the `/tiles/*` block
- `frontend/vite.config.ts` — add the `/tiles` dev proxy entry
- `frontend/src/shore/ShoreApp.tsx` — three new raster layers
- `frontend/src/shore/ShoreApp.test.ts` — cover the new tilejson URLs
- `.github/workflows/ci.yml` — a tile smoke-test in the `compose` job

---

### Task 1: Extract `fetch_grid()` from `_subset()`

**Files:**
- Modify: `backend/dhruva/sources/copernicus.py`
- Test: `backend/tests/test_copernicus_fetch_grid.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `fetch_grid(dataset_id: str, native_vars: list[str], *, lat_min: float, lat_max: float, lon_min: float, lon_max: float, start: dt.datetime, end: dt.datetime, username: str | None = None, password: str | None = None) -> xr.Dataset`, exported from `dhruva.sources.copernicus`. Task 2 calls this directly.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_copernicus_fetch_grid.py
"""fetch_grid is the box-general core _subset already had, extracted so the
COG generator can call it directly instead of duplicating the kwarg-building
logic or reaching into another module's _-prefixed method. This test proves
the extraction is behaviour-preserving: _subset must still pass the identical
kwargs it always did, just routed through fetch_grid now.
"""

import datetime as dt
from unittest.mock import MagicMock, patch

from dhruva.sources.copernicus import fetch_grid


def test_fetch_grid_builds_the_expected_open_dataset_kwargs():
    fake_ds = MagicMock()
    fake_ds.load.return_value = "loaded"
    with patch("copernicusmarine.open_dataset", return_value=fake_ds) as mock_open:
        result = fetch_grid(
            "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            ["thetao"],
            lat_min=6.0, lat_max=24.0, lon_min=66.0, lon_max=94.0,
            start=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
            end=dt.datetime(2026, 9, 14, 6, tzinfo=dt.UTC),
        )
    mock_open.assert_called_once_with(
        dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
        variables=["thetao"],
        minimum_latitude=6.0, maximum_latitude=24.0,
        minimum_longitude=66.0, maximum_longitude=94.0,
        start_datetime=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
        end_datetime=dt.datetime(2026, 9, 14, 6, tzinfo=dt.UTC),
    )
    assert result == "loaded"


def test_fetch_grid_adds_credentials_only_when_given():
    fake_ds = MagicMock()
    fake_ds.load.return_value = "loaded"
    with patch("copernicusmarine.open_dataset", return_value=fake_ds) as mock_open:
        fetch_grid(
            "d", ["v"], lat_min=0, lat_max=1, lon_min=0, lon_max=1,
            start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            end=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            username="u", password="p",
        )
    assert mock_open.call_args.kwargs["username"] == "u"
    assert mock_open.call_args.kwargs["password"] == "p"


def test_subset_delegates_to_fetch_grid_with_its_narrowed_tile():
    """The existing per-point path must be untouched by this refactor."""
    from dhruva.sources.copernicus import CopernicusAdapter
    from dhruva.sources.cache import CacheKey

    adapter = CopernicusAdapter()
    key = CacheKey(
        dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
        lat_min=10.9, lat_max=11.2, lon_min=79.8, lon_max=80.1,
        time_start=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
        time_end=dt.datetime(2026, 9, 14, 6, tzinfo=dt.UTC),
    )
    fake_ds = MagicMock()
    fake_ds.load.return_value = "loaded"
    with patch("copernicusmarine.open_dataset", return_value=fake_ds) as mock_open:
        adapter._subset(
            type("E", (), {"id": "copernicus_phy_hourly", "dataset_id": key.dataset_id})(),
            ["thetao"],
            key,
        )
    called = mock_open.call_args.kwargs
    assert called["minimum_latitude"] == 10.9
    assert called["maximum_latitude"] == 11.2
    # Surface-only for copernicus_phy_hourly, unchanged from before the refactor.
    assert called["minimum_depth"] == 0.0
    assert called["maximum_depth"] == 1.0
```

Check `CacheKey`'s exact field names against `backend/dhruva/sources/cache.py` before running this — the plan's guess (`dataset_id, lat_min, lat_max, lon_min, lon_max, time_start, time_end`) matches what `_subset` reads (`key.lat_min` etc., confirmed by reading the file), but confirm the dataclass constructor accepts them as keyword args in this order.

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_copernicus_fetch_grid.py -v`
Expected: FAIL — `fetch_grid` not defined.

- [ ] **Step 3: Extract `fetch_grid()` and make `_subset()` call it**

In `backend/dhruva/sources/copernicus.py`, add:

```python
def fetch_grid(
    dataset_id: str,
    native_vars: list[str],
    *,
    lat_min: float,
    lat_max: float,
    lon_min: float,
    lon_max: float,
    start: dt.datetime,
    end: dt.datetime,
    username: str | None = None,
    password: str | None = None,
    **extra: float,
) -> xr.Dataset:
    """Blocking. Callers on the event loop must run this in a thread.

    The box-general core of what was _subset()'s body — extracted so the COG
    generator (dhruva.geo.generate_cogs) can fetch a DEMO_BBOX-sized grid the
    same way _subset fetches a small per-point tile, without duplicating the
    kwarg-building or reaching into a _-prefixed method from outside this
    module. **extra passes through minimum_depth/maximum_depth (or any future
    open_dataset kwarg) untouched — _subset's surface-only override for
    copernicus_phy_hourly must keep reaching open_dataset exactly as it did
    before this extraction.
    """
    import copernicusmarine as cm

    kwargs: dict[str, object] = dict(
        dataset_id=dataset_id,
        variables=native_vars,
        minimum_latitude=lat_min,
        maximum_latitude=lat_max,
        minimum_longitude=lon_min,
        maximum_longitude=lon_max,
        start_datetime=start,
        end_datetime=end,
        **extra,
    )
    if username:
        kwargs["username"] = username
        kwargs["password"] = password
    return cm.open_dataset(**kwargs).load()
```

Then replace `_subset`'s body to call it:

```python
def _subset(self, entry: DatasetEntry, native: list[str], key: CacheKey) -> xr.Dataset:
    """Blocking. Runs in a worker thread."""
    depth_kwargs: dict[str, float] = {}
    if entry.id == "copernicus_phy_hourly":
        depth_kwargs = {"minimum_depth": 0.0, "maximum_depth": 1.0}
    return fetch_grid(
        entry.dataset_id,
        native,
        lat_min=key.lat_min,
        lat_max=key.lat_max,
        lon_min=key.lon_min,
        lon_max=key.lon_max,
        start=key.time_start,
        end=key.time_end,
        username=self.username,
        password=self.password,
        **depth_kwargs,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/test_copernicus_fetch_grid.py -v`
Expected: 3 passed.

- [ ] **Step 5: Run the full backend suite**

Run: `set -a; . ./.env; set +a; export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@localhost:55432/dhruva"; .venv/bin/python -m pytest backend/tests -q`
Expected: all green, no regressions — this is the proof the refactor did not change `_subset`'s external behavior.

- [ ] **Step 6: Lint and type-check**

```bash
.venv/bin/ruff check backend/ && .venv/bin/ruff format --check backend/ && .venv/bin/pyright
```

- [ ] **Step 7: Commit**

```bash
git add backend/dhruva/sources/copernicus.py backend/tests/test_copernicus_fetch_grid.py
git commit -m "sources: extract fetch_grid from _subset for box-general reuse"
```

---

### Task 2: COG generation script

**Files:**
- Modify: `backend/pyproject.toml`
- Create: `backend/dhruva/geo/generate_cogs.py`
- Test: `backend/tests/test_generate_cogs.py`

**Interfaces:**
- Consumes: `fetch_grid` from Task 1's `dhruva.sources.copernicus`; `Registry.load` and `DatasetEntry` from `dhruva.sources.registry`; `DEMO_BBOX` from `dhruva.sources.cache`.
- Produces: `write_cog(da: xr.DataArray, path: Path) -> None`; `python -m dhruva.geo.generate_cogs` writing `data/cogs/{sst,chlorophyll,wave_height}.tif`.

- [ ] **Step 1: Add `rioxarray`**

In `backend/pyproject.toml`'s `geo` extra:

```toml
geo = [
    "shapely>=2.0",
    "pyproj>=3.7",
    "geopandas>=1.0",
    "sqlalchemy[asyncio]>=2.0",
    "rioxarray>=0.17",
]
```

```bash
cd backend && uv pip install -e ".[dev,data,geo,graph]" --python ../.venv/bin/python
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_generate_cogs.py
"""write_cog is the one piece of generate_cogs.py that doesn't need live
network — a small synthetic DataArray in, a real georeferenced COG out. The
live Copernicus call itself is exercised manually (python -m
dhruva.geo.generate_cogs), not in CI, matching how no existing test hits
Copernicus live.
"""

import numpy as np
import rasterio
import xarray as xr

from dhruva.geo.generate_cogs import write_cog


def test_write_cog_produces_a_valid_georeferenced_single_band_file(tmp_path):
    lat = np.linspace(6.0, 24.0, 10)
    lon = np.linspace(66.0, 94.0, 10)
    data = np.random.rand(10, 10).astype("float32")
    da = xr.DataArray(data, coords={"lat": lat, "lon": lon}, dims=["lat", "lon"], name="sst")

    out = tmp_path / "sst.tif"
    write_cog(da, out)

    assert out.exists()
    with rasterio.open(out) as src:
        assert src.count == 1
        assert src.crs.to_epsg() == 4326
        bounds = src.bounds
        assert 66.0 <= bounds.left <= bounds.right <= 94.0
        assert 6.0 <= bounds.bottom <= bounds.top <= 24.0
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_generate_cogs.py -v`
Expected: FAIL — `dhruva.geo.generate_cogs` not found.

- [ ] **Step 4: Implement `generate_cogs.py`**

```python
# backend/dhruva/geo/generate_cogs.py
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

import xarray as xr

from dhruva.sources.cache import DEMO_BBOX
from dhruva.sources.copernicus import fetch_grid
from dhruva.sources.registry import Registry

_DATA_DIR = Path(os.environ.get("DHRUVA_DATA_DIR", str(Path(__file__).resolve().parents[3] / "data")))
COG_DIR = _DATA_DIR / "cogs"

# (output filename, registry dataset id, canonical variable name, native var name)
_TARGETS = (
    ("sst.tif", "copernicus_phy_hourly", "sst", "thetao"),
    ("wave_height.tif", "copernicus_wav", "wave_height", "VHM0"),
    ("chlorophyll.tif", "copernicus_bgc_pft", "chlorophyll", "chl"),
)


def write_cog(da: xr.DataArray, path: Path) -> None:
    """A 2D (lat, lon) DataArray to a Cloud-Optimized GeoTIFF at path.

    set_spatial_dims is required before write_crs: Copernicus data's spatial
    dims are named lat/lon, not rioxarray's default x/y, and without this the
    CRS metadata silently does not attach to the right axes.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    (
        da.rio.set_spatial_dims(x_dim="lon", y_dim="lat")
        .rio.write_crs("EPSG:4326")
        .rio.to_raster(str(path), driver="COG")
    )


async def _fetch_one(registry: Registry, entry_id: str, native_var: str) -> xr.Dataset:
    entry = registry.by_id(entry_id)
    lat_min, lat_max, lon_min, lon_max = DEMO_BBOX
    end = dt.datetime.now(dt.UTC)
    start = end - dt.timedelta(hours=6)
    depth_kwargs: dict[str, float] = {}
    if entry_id == "copernicus_phy_hourly":
        depth_kwargs = {"minimum_depth": 0.0, "maximum_depth": 1.0}
    return await asyncio.to_thread(
        fetch_grid,
        entry.dataset_id,
        [native_var],
        lat_min=lat_min,
        lat_max=lat_max,
        lon_min=lon_min,
        lon_max=lon_max,
        start=start,
        end=end,
        username=os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"),
        password=os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"),
        **depth_kwargs,
    )


async def main() -> None:
    registry = Registry.load(os.environ.get("DHRUVA_REGISTRY", "data/registry.yaml"))
    for filename, entry_id, canonical_var, native_var in _TARGETS:
        ds = await _fetch_one(registry, entry_id, native_var)
        da = ds[native_var]
        if "time" in da.dims:
            da = da.isel(time=-1)
        if "depth" in da.dims:
            da = da.isel(depth=0)
        write_cog(da, COG_DIR / filename)
        print(f"wrote {COG_DIR / filename} for {canonical_var}")


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `.venv/bin/python -m pytest backend/tests/test_generate_cogs.py -v`
Expected: 1 passed.

- [ ] **Step 6: Run the full backend suite, lint, types**

```bash
set -a; . ./.env; set +a; export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@localhost:55432/dhruva"
.venv/bin/python -m pytest backend/tests -q
.venv/bin/ruff check backend/ && .venv/bin/ruff format --check backend/ && .venv/bin/pyright
```

- [ ] **Step 7: Run it live, once, to produce real COGs for later tasks to serve**

```bash
set -a; . ./.env; set +a
.venv/bin/python -m dhruva.geo.generate_cogs
ls -la data/cogs/
```

Expected: three `.tif` files. If this fails on a Copernicus auth or network
error, Tasks 3-5 can still be implemented and tested against a hand-made
synthetic COG (`write_cog` on a small test `DataArray`, same as the unit test)
substituted into `data/cogs/` — note this explicitly if it happens, do not
silently skip the task.

- [ ] **Step 8: Commit**

```bash
git add backend/pyproject.toml backend/dhruva/geo/generate_cogs.py backend/tests/test_generate_cogs.py
git commit -m "geo: add the COG generation script for shore's raster layers"
```

---

### Task 3: The TiTiler service

**Files:**
- Create: `titiler/main.py`, `titiler/requirements.txt`, `titiler/Dockerfile`
- Modify: `docker-compose.yml`

**Interfaces:**
- Consumes: COG files at `data/cogs/*.tif` (Task 2's output), mounted read-only.
- Produces: a running service on its own port, reachable at `/cog/tiles/{tms}/{z}/{x}/{y}` and `/cog/{tms}/tilejson.json` (TiTiler's own routes, not custom).

- [ ] **Step 1: Write the service**

```python
# titiler/main.py
"""Dynamic tile server for Shore Console's raster layers. Deliberately its own
service, not a route on the api container: it needs GDAL/rasterio at the OS
level, a materially heavier footprint than the rest of the backend, and after
this session's own api crash-loop (a heavy dependency pulled in at module
import time) that coupling is exactly what to avoid.
"""

from fastapi import FastAPI
from starlette.middleware.cors import CORSMiddleware
from titiler.core.errors import DEFAULT_STATUS_CODES, add_exception_handlers
from titiler.core.factory import TilerFactory

app = FastAPI(title="dhruva-titiler")
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

cog = TilerFactory()
app.include_router(cog.router, tags=["Cloud Optimized GeoTIFF"])
add_exception_handlers(app, DEFAULT_STATUS_CODES)


@app.get("/healthz")
def ping() -> dict[str, str]:
    return {"ping": "pong"}
```

```
# titiler/requirements.txt
titiler.core>=0.19
uvicorn[standard]>=0.32
```

```dockerfile
# titiler/Dockerfile
FROM ghcr.io/osgeo/gdal:ubuntu-small-3.9.2

RUN apt-get update && apt-get install -y --no-install-recommends python3-pip && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py .

EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
```

- [ ] **Step 2: Add the service to `docker-compose.yml`**

```yaml
  titiler:
    build:
      context: ./titiler
    volumes:
      - ./data/cogs:/data/cogs:ro
    ports:
      - "${TITILER_HOST_PORT:-8001}:8000"
    healthcheck:
      test: ["CMD-SHELL", "python3 -c \"import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/healthz',timeout=3).status==200 else 1)\""]
```

Add `TITILER_HOST_PORT=8001` to `.env.example`, matching the existing
`API_HOST_PORT`/`POSTGRES_HOST_PORT` host-port-avoids-collisions convention.

- [ ] **Step 3: Build and verify it serves a real tile**

```bash
docker compose build titiler
docker compose up -d titiler
sleep 3
curl -s http://localhost:8001/healthz
curl -s -o /tmp/test-tile.png -w "%{http_code}\n" \
  "http://localhost:8001/cog/tiles/WebMercatorQuad/2/1/1.png?url=file:///data/cogs/sst.tif&rescale=18,33&colormap_name=thermal"
file /tmp/test-tile.png
```

Expected: `healthz` returns `{"ping":"pong"}`; the tile request returns `200`
and `/tmp/test-tile.png` is identified as a PNG image. If `data/cogs/sst.tif`
does not exist yet (Task 2's live run failed), use whichever COG Task 2
produced as a substitute — the point is proving TiTiler itself serves a real
file, independent of which variable.

- [ ] **Step 4: Commit**

```bash
git add titiler/ docker-compose.yml .env.example
git commit -m "infra: add the titiler service for shore's raster layers"
```

---

### Task 4: Proxy wiring

**Files:**
- Modify: `deploy/Caddyfile`
- Modify: `frontend/vite.config.ts`

**Interfaces:**
- Consumes: the `titiler` service from Task 3.
- Produces: `/tiles/*` reachable identically from Caddy (deployed) and the Vite dev proxy (local dev).

- [ ] **Step 1: Add the Caddy block**

```
# deploy/Caddyfile
:80 {
	encode gzip

	handle /api/* {
		uri strip_prefix /api
		reverse_proxy api:8000
	}

	handle /tiles/* {
		uri strip_prefix /tiles
		reverse_proxy titiler:8000
	}

	handle {
		reverse_proxy api:8000
	}
}
```

- [ ] **Step 2: Add the Vite dev proxy entry**

```typescript
// frontend/vite.config.ts
export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
      '/tiles': {
        target: 'http://localhost:8001',
        rewrite: (path) => path.replace(/^\/tiles/, ''),
      },
    },
  },
})
```

- [ ] **Step 3: Verify manually**

```bash
curl -s -o /dev/null -w "%{http_code}\n" \
  "http://localhost:8081/tiles/cog/tiles/WebMercatorQuad/2/1/1.png?url=file:///data/cogs/sst.tif&rescale=18,33&colormap_name=thermal"
```

Expected: `200`, through Caddy (port 8081 per `docs/STATUS.md`'s documented
host ports), proving the `/tiles/*` strip-prefix routes correctly end to end.

- [ ] **Step 4: Commit**

```bash
git add deploy/Caddyfile frontend/vite.config.ts
git commit -m "infra: proxy /tiles to titiler, matching the existing /api pattern"
```

---

### Task 5: Frontend raster layers

**Files:**
- Modify: `frontend/src/shore/ShoreApp.tsx`
- Modify: `frontend/src/shore/ShoreApp.test.ts`

**Interfaces:**
- Consumes: nothing new exported elsewhere — this is the leaf of the raster pipeline.
- Produces: `tilejsonUrl(variable: "sst" | "chlorophyll" | "wave_height"): string`, exported for the test to check without mounting the map.

- [ ] **Step 1: Write the failing test**

```typescript
// appended to frontend/src/shore/ShoreApp.test.ts
import { tilejsonUrl } from "./ShoreApp";

describe("tilejsonUrl", () => {
  it("builds the SST layer URL with its rescale and colormap", () => {
    const url = tilejsonUrl("sst");
    expect(url).toContain("/tiles/cog/WebMercatorQuad/tilejson.json");
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fsst.tif");
    expect(url).toContain("rescale=18%2C33");
    expect(url).toContain("colormap_name=thermal");
  });

  it("builds the chlorophyll layer URL with its own rescale and colormap", () => {
    const url = tilejsonUrl("chlorophyll");
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fchlorophyll.tif");
    expect(url).toContain("rescale=0%2C5");
    expect(url).toContain("colormap_name=algae");
  });

  it("builds the wave-height layer URL with its own rescale and colormap", () => {
    const url = tilejsonUrl("wave_height");
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fwave_height.tif");
    expect(url).toContain("rescale=0%2C8");
    expect(url).toContain("colormap_name=blues");
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `tilejsonUrl` not exported.

- [ ] **Step 3: Implement in `ShoreApp.tsx`**

Add near the top of the file, alongside `displayStatus` (both exported, both
pure):

```typescript
const RASTER_LAYERS: Record<string, { file: string; rescale: string; colormap: string }> = {
  sst: { file: "sst.tif", rescale: "18,33", colormap: "thermal" },
  chlorophyll: { file: "chlorophyll.tif", rescale: "0,5", colormap: "algae" },
  wave_height: { file: "wave_height.tif", rescale: "0,8", colormap: "blues" },
};

/** The MapLibre raster source URL for one layer. Pure and exported separately
 * from the component so the URL construction is testable without mounting
 * the map — same pattern as displayStatus and verdictOf elsewhere in this
 * codebase. */
export function tilejsonUrl(variable: keyof typeof RASTER_LAYERS): string {
  const { file, rescale, colormap } = RASTER_LAYERS[variable];
  const params = new URLSearchParams({
    url: `file:///data/cogs/${file}`,
    rescale,
    colormap_name: colormap,
  });
  return `/tiles/cog/WebMercatorQuad/tilejson.json?${params.toString()}`;
}
```

Extend `layersOn` state (already built for `pfz`/`boundaries` in the earlier
round) to the three new keys:

```typescript
  const [layersOn, setLayersOn] = useState({
    pfz: true,
    boundaries: true,
    sst: false,
    chlorophyll: false,
    wave_height: false,
  });
```

Wire the three currently-decorative `LayerBtn`s the same way `PFZ`/`IMBL-MPA`
already are:

```typescript
                  <LayerBtn
                    label="SST"
                    active={layersOn.sst}
                    onClick={() => setLayersOn((s) => ({ ...s, sst: !s.sst }))}
                  />
                  <LayerBtn
                    label="Chlorophyll"
                    active={layersOn.chlorophyll}
                    onClick={() => setLayersOn((s) => ({ ...s, chlorophyll: !s.chlorophyll }))}
                  />
                  <LayerBtn
                    label="Wave Height"
                    active={layersOn.wave_height}
                    onClick={() => setLayersOn((s) => ({ ...s, wave_height: !s.wave_height }))}
                  />
```

Add the three `<Source type="raster">` blocks alongside the existing
boundaries/PFZ `<Source>`s:

```typescript
                {layersOn.sst && (
                  <Source id="sst" type="raster" url={tilejsonUrl("sst")} tileSize={256}>
                    <Layer id="sst-layer" type="raster" paint={{ "raster-opacity": 0.7 }} />
                  </Source>
                )}
                {layersOn.chlorophyll && (
                  <Source id="chlorophyll" type="raster" url={tilejsonUrl("chlorophyll")} tileSize={256}>
                    <Layer id="chlorophyll-layer" type="raster" paint={{ "raster-opacity": 0.7 }} />
                  </Source>
                )}
                {layersOn.wave_height && (
                  <Source id="wave-height" type="raster" url={tilejsonUrl("wave_height")} tileSize={256}>
                    <Layer id="wave-height-layer" type="raster" paint={{ "raster-opacity": 0.7 }} />
                  </Source>
                )}
```

- [ ] **Step 4: Run tests, type-check, lint, build**

```bash
cd frontend
npm test
npx tsc -b --force
npm run lint
npm run build
```

Expected: all clean. `npm run build` matters here specifically — it is the
check that already caught two real bugs this project (`Cannot find module`,
`--jsx not set`) that `npm test` alone missed.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/shore/ShoreApp.tsx frontend/src/shore/ShoreApp.test.ts
git commit -m "shore: add SST, chlorophyll and wave-height raster layers"
```

---

### Task 6: CI smoke test

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: the `compose` job's already-running stack.
- Produces: a CI failure if `titiler` cannot serve a tile from a checked-in fixture COG.

- [ ] **Step 1: Add a tiny fixture COG for CI**

CI has no Copernicus credentials, so it cannot run `generate_cogs.py`. Commit
one small, already-generated COG as a fixture:

```bash
.venv/bin/python -c "
import numpy as np, xarray as xr
from pathlib import Path
from dhruva.geo.generate_cogs import write_cog
lat = np.linspace(6.0, 24.0, 5)
lon = np.linspace(66.0, 94.0, 5)
da = xr.DataArray(np.random.rand(5, 5).astype('float32'), coords={'lat': lat, 'lon': lon}, dims=['lat', 'lon'])
write_cog(da, Path('eval/fixtures/sst-fixture.tif'))
"
mkdir -p eval/fixtures
git add eval/fixtures/sst-fixture.tif
```

- [ ] **Step 2: Extend the `compose` job**

```yaml
  compose:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Gate 1 — stack comes up and /health returns 200
        run: |
          cp .env.example .env
          {
            echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)"
            echo "LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 16)"
            echo "LANGFUSE_SALT=$(openssl rand -hex 16)"
            echo "LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)"
          } >> .env
          mkdir -p data/cogs
          cp eval/fixtures/sst-fixture.tif data/cogs/sst.tif
          docker compose up -d --build --wait --wait-timeout 300
          curl -fsS http://localhost:8000/health | tee /dev/stderr | grep -q '"status":"ok"'
          curl -fsS http://localhost:8000/health/ready | tee /dev/stderr | grep -q '"ready":true'
          curl -fsS "http://localhost:8001/cog/tiles/WebMercatorQuad/2/1/1.png?url=file:///data/cogs/sst.tif&rescale=18,33&colormap_name=thermal" -o /tmp/tile.png
          file /tmp/tile.png | grep -q "PNG image data"
          docker compose down -v
```

- [ ] **Step 3: Verify locally before pushing**

```bash
docker compose down -v
cp .env.example .env
echo "POSTGRES_PASSWORD=$(openssl rand -hex 16)" >> .env
echo "LANGFUSE_NEXTAUTH_SECRET=$(openssl rand -hex 16)" >> .env
echo "LANGFUSE_SALT=$(openssl rand -hex 16)" >> .env
echo "LANGFUSE_ENCRYPTION_KEY=$(openssl rand -hex 32)" >> .env
mkdir -p data/cogs && cp eval/fixtures/sst-fixture.tif data/cogs/sst.tif
docker compose up -d --build --wait --wait-timeout 300
curl -fsS http://localhost:8000/health
curl -fsS "http://localhost:8001/cog/tiles/WebMercatorQuad/2/1/1.png?url=file:///data/cogs/sst.tif&rescale=18,33&colormap_name=thermal" -o /tmp/tile.png
file /tmp/tile.png
docker compose down -v
```

Expected: `/health` OK, `/tmp/tile.png` is a real PNG.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml eval/fixtures/sst-fixture.tif
git commit -m "ci: smoke-test the titiler service with a fixture COG"
```
