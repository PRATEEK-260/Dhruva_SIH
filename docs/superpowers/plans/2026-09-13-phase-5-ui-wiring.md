# Phase 5 UI Wiring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A real HTTP endpoint runs the DHRUVA graph end-to-end, and both the Boat PWA and Shore Console render real data through it instead of hardcoded mock content.

**Architecture:** One new FastAPI router wraps the already-compiled LangGraph graph (`dhruva.graph.build.arun`) and logs each request. A second new router exposes PostGIS boundary/zone/PFZ data as GeoJSON. The Boat PWA gains a third action (text-query "Ask", alongside the existing Scan/Speak) that calls the first router and renders through its existing verdict-card UI. The Shore Console replaces its hardcoded marker, layer buttons, and fleet list with data fetched from both routers.

**Tech Stack:** FastAPI · asyncpg · Pydantic v2 (existing) · React 19 · react-map-gl/maplibre (existing) · `qrcode` npm package (new)

**Spec:** `docs/superpowers/specs/2026-09-13-phase-5-ui-wiring-design.md`

## Global Constraints

- Every boundary/zone GeoJSON feature carries `indicative: true` in its properties — never inferred, never omitted (CLAUDE.md).
- Every PFZ GeoJSON feature carries `source_url` and `fetched_at` (CLAUDE.md).
- `advisory_log` is a request log, not vessel tracking — its module docstring says so explicitly, since no boat ever reports a position back to shore in this architecture (one-directional, no uplink).
- `risk_class` on the wire is always lowercase-with-underscore (`"safe"` | `"caution"` | `"no_go"` | `"unknown"`, matching `backend/dhruva/codec/fields.py`'s `RISK_CLASSES`) — never the uppercase display label. This exact mismatch already caused one real bug (`BoatApp.tsx`'s `verdictOf`); `FleetItem` gets the same fix in this plan rather than repeating it.
- DB connections follow the existing per-call pattern in `graph/build.py`'s `geo()` node: `asyncpg.connect(dsn, timeout=5)`, closed in a `finally` — no new pooling introduced.
- Every advisory response carries the fixed notice from `app.py`'s `ADVISORY_NOTICE`, regardless of what the graph produced.
- Voice, Boat PWA offline infrastructure (service worker/Dexie/manifest), Shore's raster/tile layers, and the broadcast composer are explicitly out of scope — do not build them as part of this plan.
- Commits: `area: imperative summary`, no AI co-author trailer (project convention).

---

## File Structure

**Create:**
- `backend/dhruva/api/schema.sql` — `advisory_log` table
- `backend/dhruva/api/store.py` — `apply_schema`, `insert_advisory`, `recent_advisories`
- `backend/dhruva/api/advisory.py` — `POST /advisory`, `GET /advisory/recent`
- `backend/dhruva/geo/layers.py` — `all_boundaries_geojson`, `all_zones_geojson`, `recent_pfz_geojson`
- `backend/dhruva/api/geo.py` — `GET /geo/boundaries`, `/geo/zones`, `/geo/pfz`
- `frontend/src/shared/api/client.ts` — `postAdvisory`, `fetchRecentAdvisories`, `fetchGeoLayer`
- `frontend/src/shared/api/client.test.ts`
- `backend/tests/test_advisory_api.py`
- `backend/tests/test_geo_api.py`
- `backend/tests/test_advisory_store.py`

**Modify:**
- `backend/dhruva/app.py` — register the two new routers
- `frontend/vite.config.ts` — dev-server proxy for `/api` → `http://localhost:8000`
- `frontend/package.json` — add `qrcode` + `@types/qrcode`
- `frontend/src/boat/BoatApp.tsx` — add the "Ask" flow
- `frontend/src/boat/BoatApp.test.ts` — cover the new flow
- `frontend/src/shore/ShoreApp.tsx` — wire layers + fleet list to real data, fix `FleetItem`'s status comparison

---

### Task 1: `advisory_log` persistence

**Files:**
- Create: `backend/dhruva/api/schema.sql`
- Create: `backend/dhruva/api/store.py`
- Test: `backend/tests/test_advisory_store.py`

**Interfaces:**
- Consumes: nothing new (plain `asyncpg.Connection`).
- Produces:
  - `apply_schema(conn: asyncpg.Connection) -> None`
  - `insert_advisory(conn: asyncpg.Connection, *, boat_class: str, lat: float, lon: float, risk_class: str) -> None`
  - `recent_advisories(conn: asyncpg.Connection, *, limit: int = 20) -> list[dict[str, Any]]` — each dict has `id, boat_class, lat, lon, risk_class, issued_at`

- [ ] **Step 1: Write `schema.sql`**

```sql
-- advisory_log is a REQUEST LOG, not vessel tracking. No boat ever reports a
-- position back to shore in this architecture (CLAUDE.md: no team transmits,
-- the NavIC uplink is ISRO's) — this table records that an advisory was
-- asked for, at what position, and what verdict came back. Never read a row
-- here as "this boat is currently there."
CREATE TABLE IF NOT EXISTS advisory_log (
    id          bigserial PRIMARY KEY,
    boat_class  text NOT NULL,
    lat         double precision NOT NULL,
    lon         double precision NOT NULL,
    risk_class  text NOT NULL,
    issued_at   timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS advisory_log_issued_idx ON advisory_log (issued_at DESC);
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_advisory_store.py
"""advisory_log is a request log, never vessel tracking. These tests exist to
hold that distinction, not just the CRUD."""

import os

import asyncpg
import pytest

from dhruva.api.store import apply_schema, insert_advisory, recent_advisories

pytestmark = pytest.mark.asyncio


async def _conn():
    dsn = os.environ.get("DHRUVA_DSN")
    if not dsn:
        pytest.skip("DHRUVA_DSN not set")
    try:
        return await asyncpg.connect(dsn, timeout=5)
    except OSError:
        pytest.skip("database not reachable")


async def test_insert_then_read_back():
    conn = await _conn()
    try:
        await apply_schema(conn)
        await conn.execute("DELETE FROM advisory_log")
        await insert_advisory(conn, boat_class="frp_under_12m", lat=11.05, lon=79.95, risk_class="caution")
        rows = await recent_advisories(conn, limit=10)
        assert len(rows) == 1
        assert rows[0]["boat_class"] == "frp_under_12m"
        assert rows[0]["risk_class"] == "caution"
        assert rows[0]["lat"] == pytest.approx(11.05)
    finally:
        await conn.close()


async def test_recent_advisories_orders_newest_first():
    conn = await _conn()
    try:
        await apply_schema(conn)
        await conn.execute("DELETE FROM advisory_log")
        for risk in ("safe", "caution", "no_go"):
            await insert_advisory(conn, boat_class="frp_under_12m", lat=11.0, lon=80.0, risk_class=risk)
        rows = await recent_advisories(conn, limit=10)
        assert [r["risk_class"] for r in rows] == ["no_go", "caution", "safe"]
    finally:
        await conn.close()


async def test_limit_caps_the_result_set():
    conn = await _conn()
    try:
        await apply_schema(conn)
        await conn.execute("DELETE FROM advisory_log")
        for _ in range(5):
            await insert_advisory(conn, boat_class="frp_under_12m", lat=11.0, lon=80.0, risk_class="safe")
        rows = await recent_advisories(conn, limit=2)
        assert len(rows) == 2
    finally:
        await conn.close()
```

- [ ] **Step 3: Run it to verify it fails**

Run: `set -a; . ./.env; set +a; export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@localhost:55432/dhruva"; .venv/bin/python -m pytest backend/tests/test_advisory_store.py -v`
Expected: FAIL — `dhruva.api.store` not found (or skipped if `pytest-asyncio` marker needs registering — check `backend/pyproject.toml`'s `[tool.pytest.ini_options]` for `asyncio_mode`; the existing suite already uses `pytest.mark.asyncio` elsewhere per `test_boundaries.py`, so no new config should be needed).

- [ ] **Step 4: Implement `store.py`**

```python
# backend/dhruva/api/store.py
"""The advisory request log.

This is NOT vessel tracking. No boat in this architecture ever reports a
position back to shore (CLAUDE.md: the NavIC uplink is ISRO's, no team
transmits) — this table only records that an advisory was requested, from
where, and what verdict came back. Shore Console's fleet list reads this as a
proxy for "who has been asking recently," never as "where boats currently
are."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncpg

SCHEMA_SQL = Path(__file__).with_name("schema.sql")


async def apply_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


async def insert_advisory(
    conn: asyncpg.Connection, *, boat_class: str, lat: float, lon: float, risk_class: str
) -> None:
    await conn.execute(
        "INSERT INTO advisory_log (boat_class, lat, lon, risk_class) VALUES ($1, $2, $3, $4)",
        boat_class,
        lat,
        lon,
        risk_class,
    )


async def recent_advisories(conn: asyncpg.Connection, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT id, boat_class, lat, lon, risk_class, issued_at "
        "FROM advisory_log ORDER BY issued_at DESC LIMIT $1",
        limit,
    )
    return [dict(r) for r in rows]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: same command as Step 3.
Expected: 3 passed (or 3 skipped if no local Postgres — that is an acceptable outcome locally, matching the existing `test_boundaries.py` pattern; CI's `compose` job has real Postgres).

- [ ] **Step 6: Commit**

```bash
git add backend/dhruva/api/schema.sql backend/dhruva/api/store.py backend/tests/test_advisory_store.py
git commit -m "api: add the advisory request log, explicitly not vessel tracking"
```

---

### Task 2: `POST /advisory` and `GET /advisory/recent`

**Files:**
- Create: `backend/dhruva/api/advisory.py`
- Modify: `backend/dhruva/app.py`
- Test: `backend/tests/test_advisory_api.py`

**Interfaces:**
- Consumes: `arun(query, lat, lon, **kw) -> DhruvaState` from `dhruva.graph.build` (already exists — do not reimplement graph invocation); `insert_advisory`, `apply_schema` from Task 1's `dhruva.api.store`; `BoatClass` from `dhruva.graph.state`.
- Produces: `router` (an `APIRouter`) importable as `from dhruva.api.advisory import router as advisory_router`.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_advisory_api.py
"""POST /advisory is the one new door onto the graph. These tests care about
the contract: a bad boat_class is rejected before anything runs, the response
shape matches what the frontend needs, and the capsule the response carries
actually decodes to the risk_class the response also carries — the same
band-coherence property backend/tests/test_graph_codec.py holds for node 9
directly, held here across the HTTP boundary too.
"""

from fastapi.testclient import TestClient

from dhruva.app import create_app
from dhruva.codec.codebook import split_reason
from dhruva.codec.codec import decode, from_base32
from dhruva.codec.fields import RISK_CLASSES

client = TestClient(create_app())


def test_advisory_rejects_a_bad_boat_class():
    r = client.post("/advisory", json={
        "query": "can I go out?", "lat": 11.05, "lon": 79.95, "boat_class": "rowboat",
    })
    assert r.status_code == 422


def test_advisory_returns_the_full_shape():
    r = client.post("/advisory", json={"query": "can I go out?", "lat": 11.05, "lon": 79.95})
    assert r.status_code == 200
    body = r.json()
    for key in ("narration", "risk_class", "firewall_passed", "evidence", "capsule_base32", "reason_code", "notice"):
        assert key in body, key


def test_advisory_notice_is_always_the_fixed_line():
    from dhruva.app import ADVISORY_NOTICE

    r = client.post("/advisory", json={"query": "can I go out?", "lat": 11.05, "lon": 79.95})
    assert r.json()["notice"] == ADVISORY_NOTICE


def test_advisory_capsule_band_matches_the_response_risk_class():
    r = client.post("/advisory", json={"query": "can I go out?", "lat": 11.05, "lon": 79.95})
    body = r.json()
    capsule = decode(from_base32(body["capsule_base32"]))
    band, _family, _modifier = split_reason(capsule.reason_code)
    assert RISK_CLASSES[band] == body["risk_class"]


def test_advisory_recent_is_reachable():
    r = client.get("/advisory/recent")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_advisory_api.py -v`
Expected: FAIL — 404s, since neither route exists yet.

- [ ] **Step 3: Implement `advisory.py`**

```python
# backend/dhruva/api/advisory.py
"""The one HTTP door onto the graph. Everything here is a thin wrapper: state
building and graph invocation are dhruva.graph.build.arun's job already."""

from __future__ import annotations

import datetime as dt
import os
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from dhruva.api.store import apply_schema, insert_advisory, recent_advisories
from dhruva.app import ADVISORY_NOTICE
from dhruva.graph.build import arun
from dhruva.graph.state import BoatClass

router = APIRouter(tags=["advisory"])


class AdvisoryRequest(BaseModel):
    query: str
    lat: float
    lon: float
    language: str = "en"
    boat_class: BoatClass = BoatClass.FRP_UNDER_12M
    when: dt.datetime | None = None


class AdvisoryResponse(BaseModel):
    narration: str
    risk_class: str
    firewall_passed: bool
    evidence: dict[str, Any]
    capsule_base32: str
    reason_code: int
    notice: str = ADVISORY_NOTICE


async def _connect() -> asyncpg.Connection | None:
    dsn = os.environ.get("DHRUVA_DSN")
    if not dsn:
        return None
    try:
        return await asyncpg.connect(dsn, timeout=5)
    except OSError:
        return None


@router.post("/advisory", response_model=AdvisoryResponse)
async def post_advisory(req: AdvisoryRequest) -> AdvisoryResponse:
    state = await arun(
        req.query,
        req.lat,
        req.lon,
        language=req.language,
        boat_class=req.boat_class,
        when=req.when,
    )
    risk_class = state.get("risk_class")
    risk_class_value = risk_class.value if risk_class is not None else "unknown"

    conn = await _connect()
    if conn is not None:
        try:
            await apply_schema(conn)
            await insert_advisory(
                conn,
                boat_class=req.boat_class.value,
                lat=req.lat,
                lon=req.lon,
                risk_class=risk_class_value,
            )
        finally:
            await conn.close()
    # A request log write failing (no DB configured) must never block an
    # advisory a crew is waiting on — the response still returns below.

    return AdvisoryResponse(
        narration=state.get("narration", ""),
        risk_class=risk_class_value,
        firewall_passed=state.get("firewall_passed", False),
        evidence=state.get("evidence", {}),
        capsule_base32=state.get("capsule_bits", ""),
        reason_code=state.get("reason_code", 0),
    )


@router.get("/advisory/recent")
async def get_recent_advisories(limit: int = 20) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 100)
    conn = await _connect()
    if conn is None:
        return []
    try:
        await apply_schema(conn)
        rows = await recent_advisories(conn, limit=limit)
    finally:
        await conn.close()
    return [
        {**row, "issued_at": row["issued_at"].isoformat()} for row in rows
    ]
```

- [ ] **Step 4: Register the router**

In `backend/dhruva/app.py`, add:

```python
from dhruva.api.advisory import router as advisory_router
```

and inside `create_app()`, after `app.include_router(health_router)`:

```python
    app.include_router(advisory_router)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: same command as Step 2.
Expected: 5 passed.

- [ ] **Step 6: Run the full backend suite**

Run: `set -a; . ./.env; set +a; export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@localhost:55432/dhruva"; .venv/bin/python -m pytest backend/tests -q`
Expected: all green, no regressions.

- [ ] **Step 7: Lint and type-check**

```bash
.venv/bin/ruff check backend/ && .venv/bin/ruff format --check backend/ && .venv/bin/pyright
```

- [ ] **Step 8: Commit**

```bash
git add backend/dhruva/api/advisory.py backend/dhruva/app.py backend/tests/test_advisory_api.py
git commit -m "api: add POST /advisory, the first door onto the graph"
```

---

### Task 3: `/geo/boundaries`, `/geo/zones`, `/geo/pfz`

**Files:**
- Create: `backend/dhruva/geo/layers.py`
- Create: `backend/dhruva/api/geo.py`
- Modify: `backend/dhruva/app.py`
- Test: `backend/tests/test_geo_api.py`

**Interfaces:**
- Consumes: `boundary_line`, `maritime_zone`, `pfz_advisory` tables (already exist, `backend/dhruva/geo/schema.sql`).
- Produces: `router` importable as `from dhruva.api.geo import router as geo_router`; `all_boundaries_geojson(conn)`, `all_zones_geojson(conn)`, `recent_pfz_geojson(conn)` each returning a GeoJSON `FeatureCollection` dict.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_geo_api.py
"""Every rendered EEZ/IMBL/MPA line carries the indicative flag (CLAUDE.md);
every PFZ row carries source_url and fetched_at. These are the two facts a
judge or a fisherman could otherwise mistake for more authority than the data
has, so they are pinned here rather than trusted to the frontend alone.
"""

from fastapi.testclient import TestClient

from dhruva.app import create_app

client = TestClient(create_app())


def _get_or_skip(path: str):
    r = client.get(path)
    if r.status_code == 503:
        import pytest

        pytest.skip("database not reachable")
    return r


def test_boundaries_is_a_feature_collection_with_indicative_flags():
    r = _get_or_skip("/geo/boundaries")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    for feature in body["features"]:
        assert feature["properties"]["indicative"] is True


def test_zones_is_a_feature_collection_with_indicative_flags():
    r = _get_or_skip("/geo/zones")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    for feature in body["features"]:
        assert feature["properties"]["indicative"] is True


def test_pfz_carries_source_url_and_fetched_at_on_every_feature():
    r = _get_or_skip("/geo/pfz")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    for feature in body["features"]:
        assert feature["properties"]["source_url"]
        assert feature["properties"]["fetched_at"]
```

- [ ] **Step 2: Run it to verify it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_geo_api.py -v`
Expected: FAIL — 404s.

- [ ] **Step 3: Implement `geo/layers.py`**

```python
# backend/dhruva/geo/layers.py
"""Whole-table GeoJSON for map display.

boundaries.py's nearest_boundaries/zones_containing are point-relative — "what
is closest to THIS lat/lon" — which is what the boat needs. Shore Console
needs everything in view at once, so these read the full tables instead.
Every boundary/zone feature carries indicative: true; every PFZ feature
carries source_url and fetched_at (CLAUDE.md).
"""

from __future__ import annotations

from typing import Any

import asyncpg


async def all_boundaries_geojson(conn: asyncpg.Connection) -> dict[str, Any]:
    rows = await conn.fetch(
        "SELECT name, line_type, territory1, territory2, indicative, source_url, "
        "ST_AsGeoJSON(geom) AS geometry FROM boundary_line"
    )
    return _feature_collection(rows, ("name", "line_type", "territory1", "territory2", "indicative", "source_url"))


async def all_zones_geojson(conn: asyncpg.Connection) -> dict[str, Any]:
    rows = await conn.fetch(
        "SELECT name, zone_type, territory, sovereign, indicative, source_url, "
        "ST_AsGeoJSON(geom) AS geometry FROM maritime_zone"
    )
    return _feature_collection(rows, ("name", "zone_type", "territory", "sovereign", "indicative", "source_url"))


async def recent_pfz_geojson(conn: asyncpg.Connection) -> dict[str, Any]:
    rows = await conn.fetch(
        "SELECT region, landing_centre, bearing_deg, distance_nm, depth_m, "
        "source_url, source_name, fetched_at, ST_AsGeoJSON(geom) AS geometry "
        "FROM pfz_advisory WHERE valid_until IS NULL OR valid_until > now() "
        "ORDER BY issued_for DESC"
    )
    return _feature_collection(
        rows,
        ("region", "landing_centre", "bearing_deg", "distance_nm", "depth_m", "source_url", "source_name", "fetched_at"),
    )


def _feature_collection(rows: list[asyncpg.Record], prop_keys: tuple[str, ...]) -> dict[str, Any]:
    import json

    features = []
    for row in rows:
        props: dict[str, Any] = {}
        for key in prop_keys:
            value = row[key]
            props[key] = value.isoformat() if hasattr(value, "isoformat") else value
        features.append(
            {"type": "Feature", "geometry": json.loads(row["geometry"]), "properties": props}
        )
    return {"type": "FeatureCollection", "features": features}
```

- [ ] **Step 4: Implement `api/geo.py`**

```python
# backend/dhruva/api/geo.py
"""Boundary/zone/PFZ layers for the map, as plain GeoJSON.

No tile server exists yet (no TiTiler, no pg_tileserv) — these tables are
small enough (hundreds of rows) to ship whole over REST rather than tiled.
SST/chlorophyll/wave height are gridded rasters and need the tile pipeline
regardless; they are not part of this router.
"""

from __future__ import annotations

import os
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException

from dhruva.geo.layers import all_boundaries_geojson, all_zones_geojson, recent_pfz_geojson

router = APIRouter(prefix="/geo", tags=["geo"])


async def _connect() -> asyncpg.Connection:
    dsn = os.environ.get("DHRUVA_DSN")
    if not dsn:
        raise HTTPException(503, "DHRUVA_DSN not configured")
    try:
        return await asyncpg.connect(dsn, timeout=5)
    except OSError as exc:
        raise HTTPException(503, "database not reachable") from exc


@router.get("/boundaries")
async def get_boundaries() -> dict[str, Any]:
    conn = await _connect()
    try:
        return await all_boundaries_geojson(conn)
    finally:
        await conn.close()


@router.get("/zones")
async def get_zones() -> dict[str, Any]:
    conn = await _connect()
    try:
        return await all_zones_geojson(conn)
    finally:
        await conn.close()


@router.get("/pfz")
async def get_pfz() -> dict[str, Any]:
    conn = await _connect()
    try:
        return await recent_pfz_geojson(conn)
    finally:
        await conn.close()
```

- [ ] **Step 5: Register the router**

In `backend/dhruva/app.py`, add `from dhruva.api.geo import router as geo_router` and `app.include_router(geo_router)`.

- [ ] **Step 6: Run tests, lint, types, full suite**

```bash
.venv/bin/python -m pytest backend/tests/test_geo_api.py backend/tests -q
.venv/bin/ruff check backend/ && .venv/bin/ruff format --check backend/ && .venv/bin/pyright
```

Expected: all green (or geo tests skip cleanly with no DSN, matching the existing `test_boundaries.py` pattern).

- [ ] **Step 7: Commit**

```bash
git add backend/dhruva/geo/layers.py backend/dhruva/api/geo.py backend/dhruva/app.py backend/tests/test_geo_api.py
git commit -m "api,geo: add whole-table GeoJSON for boundaries, zones, and PFZ"
```

---

### Task 4: Frontend API client + dev proxy

**Files:**
- Modify: `frontend/vite.config.ts`
- Create: `frontend/src/shared/api/client.ts`
- Test: `frontend/src/shared/api/client.test.ts`

**Interfaces:**
- Consumes: nothing (this is the frontend's own new base layer).
- Produces:
  - `postAdvisory(req: AdvisoryRequest): Promise<AdvisoryResponse>`
  - `fetchRecentAdvisories(limit?: number): Promise<AdvisoryLogEntry[]>`
  - `fetchGeoLayer(name: "boundaries" | "zones" | "pfz"): Promise<GeoJSON.FeatureCollection>`
  - Types: `AdvisoryRequest`, `AdvisoryResponse`, `AdvisoryLogEntry`

- [ ] **Step 1: Add the Vite dev proxy**

```typescript
// frontend/vite.config.ts
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import { defineConfig } from 'vite'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  server: {
    // Matches deploy/Caddyfile's existing /api/* strip-prefix convention, so
    // the same relative fetch("/api/...") path works in dev (via this proxy)
    // and in a Caddy-fronted deployment without a code change.
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        rewrite: (path) => path.replace(/^\/api/, ''),
      },
    },
  },
})
```

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/src/shared/api/client.test.ts
import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchGeoLayer, fetchRecentAdvisories, postAdvisory } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("postAdvisory", () => {
  it("posts to /api/advisory and returns the parsed response", async () => {
    const mockResponse = {
      narration: "Conditions are within limits.",
      risk_class: "safe",
      firewall_passed: true,
      evidence: {},
      capsule_base32: "BRWZQC75355GADBL7ASLYXG7BEJGKAA",
      reason_code: 0,
      notice: "Advisory only. Follow official INCOIS and IMD warnings.",
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await postAdvisory({ query: "can I go out?", lat: 11.05, lon: 79.95 });

    expect(result).toEqual(mockResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/advisory",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws with a clear message on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(postAdvisory({ query: "x", lat: 0, lon: 0 })).rejects.toThrow();
  });

  it("throws on a non-OK response rather than returning a half-filled object", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({}) }));
    await expect(postAdvisory({ query: "x", lat: 0, lon: 0 })).rejects.toThrow();
  });
});

describe("fetchRecentAdvisories", () => {
  it("fetches /api/advisory/recent", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);
    await fetchRecentAdvisories(10);
    expect(fetchMock).toHaveBeenCalledWith("/api/advisory/recent?limit=10");
  });
});

describe("fetchGeoLayer", () => {
  it("fetches the named layer", async () => {
    const fc = { type: "FeatureCollection", features: [] };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => fc });
    vi.stubGlobal("fetch", fetchMock);
    const result = await fetchGeoLayer("boundaries");
    expect(fetchMock).toHaveBeenCalledWith("/api/geo/boundaries");
    expect(result).toEqual(fc);
  });
});
```

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `./client` not found.

- [ ] **Step 4: Implement `client.ts`**

```typescript
// frontend/src/shared/api/client.ts
// Thin fetch wrappers over the backend's /advisory and /geo routes. The /api
// prefix matches both the Vite dev proxy (vite.config.ts) and deploy/Caddyfile's
// existing strip-prefix convention, so this code is unchanged between dev and
// a Caddy-fronted deployment.
//
// FeatureCollection comes from the `geojson` package's own types (react-map-gl
// and maplibre-gl both depend on it already, so it resolves without a new
// dependency) rather than a hand-rolled interface — react-map-gl's <Source
// data={...}> prop expects exactly this type, so using it directly here means
// ShoreApp.tsx (Task 6) never needs to cast past the type checker to pass a
// fetched layer straight into <Source>. If `import type { FeatureCollection }
// from "geojson"` fails to resolve, run `npm install -D @types/geojson` first.
import type { FeatureCollection } from "geojson";

export interface AdvisoryRequest {
  query: string;
  lat: number;
  lon: number;
  language?: string;
  boat_class?: string;
}

export interface AdvisoryResponse {
  narration: string;
  risk_class: string;
  firewall_passed: boolean;
  evidence: Record<string, unknown>;
  capsule_base32: string;
  reason_code: number;
  notice: string;
}

export interface AdvisoryLogEntry {
  id: number;
  boat_class: string;
  lat: number;
  lon: number;
  risk_class: string;
  issued_at: string;
}

export type GeoFeatureCollection = FeatureCollection;

async function parseOrThrow<T>(response: Response, what: string): Promise<T> {
  if (!response.ok) {
    throw new Error(`${what} failed: HTTP ${response.status}`);
  }
  return (await response.json()) as T;
}

export async function postAdvisory(req: AdvisoryRequest): Promise<AdvisoryResponse> {
  const response = await fetch("/api/advisory", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(req),
  });
  return parseOrThrow<AdvisoryResponse>(response, "postAdvisory");
}

export async function fetchRecentAdvisories(limit = 20): Promise<AdvisoryLogEntry[]> {
  const response = await fetch(`/api/advisory/recent?limit=${limit}`);
  return parseOrThrow<AdvisoryLogEntry[]>(response, "fetchRecentAdvisories");
}

export async function fetchGeoLayer(
  name: "boundaries" | "zones" | "pfz",
): Promise<GeoFeatureCollection> {
  const response = await fetch(`/api/geo/${name}`);
  return parseOrThrow<GeoFeatureCollection>(response, `fetchGeoLayer(${name})`);
}
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 6: Type-check and lint**

```bash
cd frontend && npx tsc -b --force && npm run lint
```

- [ ] **Step 7: Commit**

```bash
git add frontend/vite.config.ts frontend/src/shared/api/client.ts frontend/src/shared/api/client.test.ts
git commit -m "frontend: add the API client and dev proxy for /advisory and /geo"
```

---

### Task 5: Boat PWA "Ask" flow

**Files:**
- Modify: `frontend/package.json` (add `qrcode`, `@types/qrcode`)
- Modify: `frontend/src/boat/BoatApp.tsx`
- Modify: `frontend/src/boat/BoatApp.test.ts`

**Interfaces:**
- Consumes: `postAdvisory` from Task 4's `../shared/api/client`; `verdictOf` (already exported from this same file).
- Produces: nothing new consumed elsewhere — this is the leaf of the Boat side.

- [ ] **Step 1: Install `qrcode`**

```bash
cd frontend && npm install qrcode && npm install -D @types/qrcode
```

- [ ] **Step 2: Write the failing test**

```typescript
// appended to frontend/src/boat/BoatApp.test.ts
import { describe, expect, it, vi, afterEach } from "vitest";
import { askAdvisory } from "./BoatApp";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("askAdvisory", () => {
  it("returns narration and a QR-ready capsule on success", async () => {
    const mockResponse = {
      narration: "Take care. Wind 22 knots, near the limit for your boat.",
      risk_class: "caution",
      firewall_passed: true,
      evidence: {},
      capsule_base32: "BRWZQC75355GADBL7ASLYXG7BEJGKAA",
      reason_code: 0b01_010_000,
      notice: "Advisory only. Follow official INCOIS and IMD warnings.",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => mockResponse }),
    );

    const result = await askAdvisory("can I go out?", "ta", "frp_under_12m");

    expect(result.narration).toBe(mockResponse.narration);
    expect(result.riskClass).toBe("caution");
    expect(result.capsuleBase32).toBe(mockResponse.capsule_base32);
  });

  it("throws a clear, catchable error on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(askAdvisory("x", "en", "frp_under_12m")).rejects.toThrow();
  });
});

describe("generateHandoffQr", () => {
  it("produces a non-empty SVG string", async () => {
    const svg = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    expect(svg).toContain("<svg");
  });

  it("is deterministic for the same capsule", async () => {
    const a = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    const b = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    expect(a).toBe(b);
  });

  it("differs for a different capsule", async () => {
    const a = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    const b = await generateHandoffQr("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    expect(a).not.toBe(b);
  });
});
```

Add `generateHandoffQr` to the import on line 886: `import { askAdvisory, generateHandoffQr } from "./BoatApp";`.

- [ ] **Step 3: Run it to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `askAdvisory`/`generateHandoffQr` not exported.

- [ ] **Step 4: Implement the Ask flow in `BoatApp.tsx`**

Add near the top, after the existing imports:

The existing `import { useState } from 'react';` line stays as-is; add these two new imports below it:

```typescript
import QRCode from 'qrcode';
import { postAdvisory } from '../shared/api/client';
```

Add, alongside `verdictOf` (both exported, both pure or near-pure so they are testable without mounting the component):

```typescript
// The demo coordinate: 11.05N 79.95E is at sea, in the EEZ and territorial
// waters, per docs/STATUS.md — the plan's original point was on land. No
// geolocation prompt is wired up this round; a real device build would read
// navigator.geolocation instead of this constant.
const DEMO_LAT = 11.05;
const DEMO_LON = 79.95;

export async function askAdvisory(query: string, lang: Language, boatClass: string) {
  const response = await postAdvisory({
    query,
    lat: DEMO_LAT,
    lon: DEMO_LON,
    language: lang,
    boat_class: boatClass,
  });
  return {
    narration: response.narration,
    riskClass: response.risk_class,
    degraded: false,
    capsuleBase32: response.capsule_base32,
  };
}

/** SVG string for the offline-handoff QR. Pure and exported separately from
 * the component, mirroring backend/dhruva/codec/qr.py's own qr_svg() — same
 * reasoning: a thin wrapper over a well-tested library is still worth its own
 * seam, since it is the one place this project's own choices (which field,
 * which error-correction level) live. */
export async function generateHandoffQr(capsuleBase32: string): Promise<string> {
  return QRCode.toString(capsuleBase32, { type: "svg" });
}
```

Inside `BoatApp()`, add state and a handler:

```typescript
  const [askText, setAskText] = useState("");
  const [asking, setAsking] = useState(false);
  const [askError, setAskError] = useState<string | null>(null);
  const [qrSvg, setQrSvg] = useState<string | null>(null);

  const handleAsk = async () => {
    if (!askText.trim()) return;
    setAsking(true);
    setAskError(null);
    try {
      const result = await askAdvisory(askText, lang, "frp_under_12m");
      setCapsule(null); // this answer did not come from a scanned capsule
      setAdvisoryText(result.narration);
      setDegraded(result.degraded);
      // risk_class flows through verdictOf below via a small state override —
      // see the isNoGo/isCaution/isSafe computation.
      setAskRiskClass(result.riskClass);
      setQrSvg(await generateHandoffQr(result.capsuleBase32));
      speak(result.narration, lang);
    } catch {
      setAskError("Could not reach the network. Try Scan QR instead.");
    } finally {
      setAsking(false);
    }
  };
```

Add one more piece of state (near `capsule`) so the verdict card can be driven by either a scanned capsule or an online answer:

```typescript
  const [askRiskClass, setAskRiskClass] = useState<string | null>(null);
```

Update the verdict computation to prefer whichever source is present:

```typescript
  const verdict = verdictOf(capsule?.risk_class ?? askRiskClass ?? undefined);
```

Update `handleScan` to clear `askRiskClass`/`qrSvg` (so a fresh scan doesn't show a stale online QR):

```typescript
  const handleScan = (res: { payload: string, advisory: { text: string, degraded: boolean }, capsule: Capsule }) => {
    setAskRiskClass(null);
    setQrSvg(null);
    setCapsule(res.capsule);
    setAdvisoryText(res.advisory.text);
    setDegraded(res.advisory.degraded);
    setIsScanning(false);
    speak(res.advisory.text, lang);
  };
```

The `{!capsule ? ... : ...}` branch needs to also treat `askRiskClass` as "there is data to show" — change the condition to `{!capsule && !askRiskClass ? ... : ...}`, and change every place inside that branch reading `capsule.wave_hs_m` etc. to guard for the ask-flow case, where there is no `Capsule` object at all — those per-field cards (Sea Conditions, Boundary Watch, PFZ) render `null` when `capsule` is absent, showing only the verdict card and narration text for an online answer:

```typescript
        {!capsule && !askRiskClass ? (
          /* unchanged "No Data" block */
        ) : (
          <>
            {/* Verdict Card, Override Notice, degraded notice: all unchanged,
                already driven by isNoGo/isCaution/isSafe/degraded/advisoryText */}

            {qrSvg && (
              <div className="bg-white rounded-xl p-4 shadow-sm border border-gray-200 mb-6 flex flex-col items-center">
                <h3 className="font-bold text-gray-800 mb-3 uppercase tracking-wider text-sm self-start">
                  Offline Handoff QR
                </h3>
                <div dangerouslySetInnerHTML={{ __html: qrSvg }} />
                <p className="text-xs text-gray-500 mt-2">Scan to reload this advisory offline.</p>
              </div>
            )}

            {capsule && (
              <>
                {/* Data Age, Sea Conditions, Boundary Watch, PFZ: unchanged,
                    only rendered when a real decoded Capsule exists */}
              </>
            )}
          </>
        )}
```

Add the Ask input above the Sticky Bottom Actions bar:

```typescript
      <div className="px-4 pb-2">
        <div className="flex gap-2">
          <input
            type="text"
            value={askText}
            onChange={(e) => setAskText(e.target.value)}
            placeholder="Ask a question (needs signal)..."
            className="flex-1 px-3 py-2 border border-gray-300 rounded-lg text-sm"
            disabled={asking}
          />
          <button
            onClick={handleAsk}
            disabled={asking || !askText.trim()}
            className="px-4 py-2 bg-slate-700 text-white rounded-lg text-sm font-bold disabled:bg-gray-300"
          >
            {asking ? "..." : "Ask"}
          </button>
        </div>
        {askError && <p className="text-xs text-danger mt-1">{askError}</p>}
      </div>
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 6: Type-check, lint, build**

```bash
cd frontend && npx tsc -b --force && npm run lint && npm run build
```

Expected: clean. `npm run build` matters here specifically — it is the check that has already caught two real bugs this project (`Cannot find module`, `--jsx not set`) that `npm test` alone missed.

- [ ] **Step 7: Commit**

```bash
git add frontend/package.json frontend/package-lock.json frontend/src/boat/BoatApp.tsx frontend/src/boat/BoatApp.test.ts
git commit -m "boat: add the online Ask flow with a QR handoff"
```

---

### Task 6: Shore Console real data

**Files:**
- Modify: `frontend/src/shore/ShoreApp.tsx`

**Interfaces:**
- Consumes: `fetchGeoLayer`, `fetchRecentAdvisories` from Task 4's `../shared/api/client`; `verdictOf` from `../boat/BoatApp` (reused rather than reimplemented — see Global Constraints).

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/shore/ShoreApp.test.ts
import { describe, expect, it } from "vitest";
import { displayStatus } from "./ShoreApp";

describe("displayStatus", () => {
  it("maps every real risk_class to its display label", () => {
    expect(displayStatus("safe")).toBe("SAFE");
    expect(displayStatus("caution")).toBe("CAUTION");
    expect(displayStatus("no_go")).toBe("NO-GO");
  });

  it("does not crash on an unrecognised value", () => {
    expect(displayStatus("unknown")).toBe("UNKNOWN");
  });
});
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `displayStatus` not exported.

- [ ] **Step 3: Implement the wiring**

Add imports:

```typescript
import { useEffect, useState } from 'react';
import { fetchGeoLayer, fetchRecentAdvisories, type AdvisoryLogEntry, type GeoFeatureCollection } from '../shared/api/client';
import { verdictOf } from '../boat/BoatApp';
import ReactMapGL, { MapProvider, Marker, Source, Layer } from 'react-map-gl/maplibre';
```

Add the exported pure display-label helper (same file, near the top, mirroring `verdictOf`'s pattern of pure-function-plus-component):

```typescript
/** risk_class ("safe" | "caution" | "no_go" | "unknown") to the display label
 * this UI already uses everywhere else (BoatApp's own verdict banners say
 * "NO-GO", not "no_go"). The one place this comparison happens, so the same
 * uppercase/lowercase mismatch that broke BoatApp's verdict card cannot
 * reappear here silently. */
export function displayStatus(riskClass: string): string {
  // No cast needed: Capsule["risk_class"] is declared as plain `string` in
  // decode.ts, so verdictOf already accepts exactly this type.
  const verdict = verdictOf(riskClass);
  if (verdict === "no_go") return "NO-GO";
  if (verdict === "caution") return "CAUTION";
  if (verdict === "safe") return "SAFE";
  return "UNKNOWN";
}
```

Inside `ShoreApp()`, add state and effects:

```typescript
  const [boundaries, setBoundaries] = useState<GeoFeatureCollection | null>(null);
  const [pfz, setPfz] = useState<GeoFeatureCollection | null>(null);
  const [fleet, setFleet] = useState<AdvisoryLogEntry[]>([]);
  const [layersOn, setLayersOn] = useState({ pfz: true, boundaries: true });

  useEffect(() => {
    fetchGeoLayer("boundaries").then(setBoundaries).catch(() => setBoundaries(null));
    fetchGeoLayer("pfz").then(setPfz).catch(() => setPfz(null));
    fetchRecentAdvisories(20).then(setFleet).catch(() => setFleet([]));
  }, []);
```

Replace the hardcoded `LayerBtn` block (only the `PFZ` and `IMBL/MPA` buttons become functional; SST/Chlorophyll/Wave Height stay decorative — no data source exists for them this round):

```typescript
                <div className="absolute top-4 left-4 flex gap-2 z-10">
                  <LayerBtn label="SST" active />
                  <LayerBtn label="Chlorophyll" />
                  <LayerBtn label="Wave Height" />
                  <LayerBtn
                    label="PFZ"
                    active={layersOn.pfz}
                    onClick={() => setLayersOn((s) => ({ ...s, pfz: !s.pfz }))}
                  />
                  <LayerBtn
                    label="IMBL/MPA"
                    active={layersOn.boundaries}
                    onClick={() => setLayersOn((s) => ({ ...s, boundaries: !s.boundaries }))}
                  />
                </div>
```

(`LayerBtn` needs an optional `onClick` prop added to its signature: `{ label: string, active?: boolean, onClick?: () => void }`, and `<button onClick={onClick} ...>`.)

Add the actual layers, inside `<ReactMapGL>`, after the existing overlay controls and before the boat `<Marker>`:

```typescript
                {layersOn.boundaries && boundaries && (
                  <Source id="boundaries" type="geojson" data={boundaries}>
                    {/* Dashed: these lines are indicative, never legal (CLAUDE.md) */}
                    <Layer
                      id="boundaries-line"
                      type="line"
                      paint={{ "line-color": "#f59e0b", "line-width": 2, "line-dasharray": [2, 2] }}
                    />
                  </Source>
                )}
                {layersOn.pfz && pfz && (
                  <Source id="pfz" type="geojson" data={pfz}>
                    <Layer
                      id="pfz-points"
                      type="circle"
                      paint={{ "circle-radius": 5, "circle-color": "#22c55e" }}
                    />
                  </Source>
                )}
                {layersOn.boundaries && boundaries && boundaries.features.length > 0 && (
                  <div className="absolute bottom-4 left-4 bg-black/75 text-white text-[10px] px-3 py-1.5 rounded shadow z-10">
                    Boundaries shown are indicative only, not a legal line.
                  </div>
                )}
```

Replace the single hardcoded boat `<Marker>` with one per fleet entry:

```typescript
                {fleet.map((entry) => (
                  <Marker key={entry.id} longitude={entry.lon} latitude={entry.lat} anchor="bottom">
                    <div className="flex flex-col items-center">
                      <div className={`p-1.5 rounded-sm shadow-lg mb-1 relative ${
                        displayStatus(entry.risk_class) === "NO-GO" ? "bg-danger" :
                        displayStatus(entry.risk_class) === "CAUTION" ? "bg-caution" : "bg-safe"
                      } text-white`}>
                        <Ship className="w-4 h-4" />
                      </div>
                      <span className="bg-black/75 text-white text-[10px] px-1.5 py-0.5 rounded shadow">
                        {entry.boat_class}
                      </span>
                    </div>
                  </Marker>
                ))}
```

Replace the `Fleet (12)` header and the hardcoded `<FleetItem>` list:

```typescript
          <h2 className="font-bold text-lg">Fleet ({fleet.length})</h2>
```

```typescript
        <div className="flex-1 overflow-y-auto">
          {fleet.length === 0 ? (
            <p className="p-4 text-sm text-gray-400">No advisories requested yet.</p>
          ) : (
            fleet.map((entry) => (
              <FleetItem
                key={entry.id}
                name={entry.boat_class}
                lat={`${entry.lat.toFixed(3)}° N`}
                lon={`${entry.lon.toFixed(3)}° E`}
                time={new Date(entry.issued_at).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })}
                status={displayStatus(entry.risk_class)}
                breach={displayStatus(entry.risk_class) !== "SAFE"}
              />
            ))
          )}
        </div>
```

`FleetItem`'s internal `statusColor` line already switches on the exact uppercase labels `displayStatus` now produces (`'SAFE'`/`'CAUTION'`/anything else → danger), so it needs no change — the fix is that its input is now guaranteed to be one of those three labels rather than an arbitrary hardcoded string.

Update the `Vessels Tracked` stat card to the same real count:

```typescript
            <StatCard icon={<Ship className="w-4 h-4 text-indigo-600" />} label="Advisories (recent)" value={String(fleet.length)} unit="" status="Live" />
```

(Renamed from "Vessels Tracked" to "Advisories (recent)" — the old label claimed live tracking this data source does not provide.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd frontend && npm test`
Expected: all pass.

- [ ] **Step 5: Type-check, lint, build**

```bash
cd frontend && npx tsc -b --force && npm run lint && npm run build
```

- [ ] **Step 6: Commit**

```bash
git add frontend/src/shore/ShoreApp.tsx frontend/src/shore/ShoreApp.test.ts
git commit -m "shore: wire boundary/PFZ layers and the fleet list to real data"
```

---

## Manual verification (needs Docker + both dev servers running)

Automated tests cover logic; this confirms the actual end-to-end wiring, the same way Gate 4's phone test could not be automated:

```bash
docker compose up -d --wait
set -a; . ./.env; set +a
export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@localhost:55432/dhruva"
curl -s -X POST http://localhost:8000/advisory -H 'content-type: application/json' \
  -d '{"query":"can I go out?","lat":11.05,"lon":79.95}' | head -c 500
```

Then, in `frontend/`: `npm run dev`, open `/boat`, type a question into Ask, confirm narration and a QR render; open `/shore`, confirm boundaries/PFZ toggle on and off and the fleet list is not the old hardcoded six entries.
