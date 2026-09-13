# Phase 5 UI wiring — Boat, Shore, and the API endpoint — design

Written 2026-09-13. Scope for this round, decided in brainstorming: the API
endpoint that runs the graph, and wiring the Boat PWA and Shore Console to real
data through it. Voice (Bhashini/Sarvam/Asterisk) and Study routes are
explicitly deferred — they are independent subsystems, not UI wiring, and each
gets its own brainstorm→spec→plan cycle later.

This does **not** attempt IMPLEMENTATION.md's Boat PWA offline infrastructure
(service worker + Dexie + manifest) or Shore's raster/vector tile layers
(TiTiler + pg_tileserv don't exist yet — confirmed absent from
`docker-compose.yml`). Those are separate, larger subsystems; see §7.

---

## 1. Why this is the shape it is

Phase 3–4 built a complete, tested graph (`query → planner → … → evidence →
codec`) and a complete, tested capsule/codebook pipeline. Neither is reachable
from outside a Python process: `backend/dhruva/api/` has exactly two routes,
`/health` and `/health/ready`. Every other piece of Phase 5 — Boat's online
"ask a question" path, Shore's broadcast composer, Voice's ASR→graph→TTS loop —
depends on *some* HTTP door onto the graph existing first. That door is the
single new piece of backend logic this round adds; everything else is wiring
already-tested pieces (the graph, the codec, PostGIS) to two already-scaffolded
frontends.

Three decisions from brainstorming shape everything below:

- **The online response carries both narration and a capsule.** Node 8's
  narration is firewall-validated English (richer than the 256-entry
  codebook, which exists specifically for the *offline* constraint). Node 9's
  capsule/base32 lets an online answer still be handed off as a QR. Returning
  both means the endpoint duplicates nothing — it is a thin HTTP wrapper over
  work the graph already does.
- **Shore's map layers are GeoJSON, not tiles.** No TiTiler/pg_tileserv exists.
  Boundaries, zones and PFZ are small enough (hundreds of rows, not a raster
  grid) to ship as plain `FeatureCollection`s over REST. SST/chlorophyll/wave
  height are explicitly out of scope this round — they are gridded rasters and
  need the tile pipeline regardless of this choice.
- **The fleet list is a request log, not vessel tracking.** CLAUDE.md's
  settled decision is one-directional: ISRO's NavIC uplink, no team
  transmits, so no boat ever reports a position back to shore in this
  architecture. "Real fleet data" therefore cannot mean live tracking without
  inventing a channel the project explicitly does not have. It can honestly
  mean *who has asked for an advisory recently* — a request log, clearly
  documented as exactly that, never conflated with position tracking.

## 2. New backend surface

### `POST /advisory` — `backend/dhruva/api/advisory.py`

```
Request:  {query: str, lat: float, lon: float, language: str = "en",
           boat_class: str = "frp_under_12m", when: datetime | None = None}
Response: {narration: str, risk_class: str, firewall_passed: bool,
           evidence: dict, capsule_base32: str, reason_code: int, notice: str}
```

Builds `initial_state(query, lat, lon, language=language,
boat_class=BoatClass(boat_class), when=when)` from `dhruva.graph.state`, calls
`await graph.ainvoke(state)` on the already-compiled graph (`dhruva.graph.build
.graph`), logs the request (§3), and shapes the response from
`state["narration"]`, `state["risk_class"]`, `state["firewall_passed"]`,
`state["evidence"]`, `state["capsule_bits"]`, `state["reason_code"]`. `notice`
is always the fixed advisory-only line (`app.py`'s existing
`ADVISORY_NOTICE`), never omitted regardless of what the graph produced.

A bad `boat_class` string (not one of `BoatClass`'s members) is a 422, not a
500 — validate before building state.

### `GET /advisory/recent?limit=20` — same file

Reads the request log, most recent first, capped at `limit` (max 100). Backs
Shore Console's fleet list (§4).

### `GET /geo/boundaries`, `GET /geo/zones`, `GET /geo/pfz` — `backend/dhruva/api/geo.py`

Each returns a GeoJSON `FeatureCollection`. Boundaries and zones read the
entire `boundary_line` / `maritime_zone` tables (not point-relative — Shore
needs everything in view, not "nearest to one point" the way the boat's own
`nearest_boundaries`/`zones_containing` do). PFZ reads `pfz_advisory` filtered
to `valid_until IS NULL OR valid_until > now()`, ordered by `issued_for DESC`.

Every boundary/zone feature's `properties` carries `indicative: true` — never
optional, never inferred client-side. Every PFZ feature's `properties` carries
`source_url` and `fetched_at` from the row. Both are direct requirements from
CLAUDE.md ("every rendered EEZ/IMBL/MPA line carries the flag"; "carry
source_url and fetched_at on every row").

## 3. New persistence

`backend/dhruva/api/store.py`, following the exact `schema.sql` +
`apply_schema(conn)` pattern already established in `geo/boundaries.py` (own
`backend/dhruva/api/schema.sql`, own `apply_schema()`):

```sql
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

The module docstring states plainly: this is a log of *requests*, not vessel
positions — no boat ever reports its position back to shore in this
architecture, and nothing about this table should ever be read as tracking.

`store.py` exports `insert_advisory(conn, boat_class, lat, lon, risk_class)`
and `recent_advisories(conn, limit)`. Connection handling matches the existing
pattern in `graph/build.py`'s `geo()` node: `asyncpg.connect(dsn, timeout=5)`
per call, closed in a `finally` — no new pooling introduced this round.

## 4. Boat PWA wiring

`BoatApp.tsx` gains a third action alongside SCAN QR / SPEAK: a text query
box, "Ask" (text only — ASR is deferred, per the Voice subsystem being out of
scope). On submit: `POST /advisory` with `{query, lat, lon, language, boat_class}`
using the boat's current position and the already-selected language.

The response renders through the **existing** verdict-card UI —
`verdictOf(risk_class)` already takes a plain string, so it needs no change
whether that string comes from a decoded `Capsule` or this new response
directly. `narration` fills the same text slot `advisoryText` already
occupies from the scan path.

New: a QR rendering of `capsule_base32`, via a new `qrcode` npm dependency
(client-side generation — this is the one new frontend dependency this round
adds). Shown alongside the narration so an online answer can still be handed
off or scanned later offline.

Failure handling matters here specifically because it's the one plausible
failure mode this whole project exists around: if the fetch fails (no
signal), the UI says so in plain language and points at "Scan QR" as the
already-working offline path — never a spinner that hangs, never a generic
error.

## 5. Shore Console wiring

`ShoreApp.tsx`: the hardcoded `<Marker>` and the five decorative `LayerBtn`s
(SST/Chlorophyll/Wave Height/PFZ/IMBL-MPA — the first three stay decorative
and inert this round, since they need the tile pipeline this round explicitly
excludes) get real behaviour for the two that can be:

- On mount, fetch `/geo/boundaries` and `/geo/pfz`. Render each as a
  `<Source type="geojson">` + `<Layer>` in `react-map-gl/maplibre`, shown or
  hidden by the existing `PFZ` and `IMBL-MPA` `LayerBtn`s (their `active` prop
  starts actually meaning something).
- Boundaries render visually distinct from a "real" line — dashed stroke plus
  a persistent on-map legend note ("indicative only, not a legal boundary") —
  so the `indicative` flag has a UI consequence, not just a JSON property
  nobody reads.
- Fetch `/advisory/recent` on mount, replacing the hardcoded `<FleetItem>`
  array. Each row becomes a real `<Marker>` (replacing the one hardcoded
  DH-007 marker) plus a fleet-list entry.
- `FleetItem`'s `status` prop currently compares against uppercase strings
  (`"SAFE"`/`"CAUTION"`) — the same mismatch class already found and fixed in
  `BoatApp.tsx`. Since this file's status now comes from a **real**
  `risk_class` (lowercase, per `fields.py`/`RISK_CLASSES`), `FleetItem` gets
  the same fix, so this bug class doesn't reappear in the one other file that
  has the identical shape.

## 6. Testing

**Backend**: FastAPI `TestClient` tests for `/advisory` — firewall_passed is
respected, `capsule_base32` decodes via the existing `from_base32`/`decode`
and its `reason_code`'s band matches the response's `risk_class`, a bad
`boat_class` is 422. Tests for `/geo/*` — valid `FeatureCollection` shape,
`indicative`/`source_url`/`fetched_at` present on every feature. Tests for
`store.py` — insert then read-back, ordering, `limit` capping.

**Frontend**: mocked-`fetch` tests for the Ask flow (success, network failure,
firewall-failed response) and for Shore's layer/fleet fetches, plus a
determinism check on QR generation from a known `capsule_base32`.

## 7. Explicitly out of scope, named rather than left implicit

- Voice: no Bhashini/Sarvam client code, no ASR, no Asterisk IVR. The `Ask`
  flow is text-in, text-and-capsule-out.
- Boat PWA offline infrastructure: no service worker, no Dexie, no manifest.
  The app is not installable and has no cached-asset offline story beyond the
  decoder already being pure JS. A real gap against IMPLEMENTATION.md's Boat
  PWA requirement, tracked for a later round.
- Shore's raster layers (SST, chlorophyll, wave height) and true vector tiles:
  blocked on standing up TiTiler + pg_tileserv, which doesn't exist.
- Broadcast composer: not built this round — it depends on deciding what
  "broadcast" means operationally (who receives it, over which of QR/
  Bluetooth/SMS), which is a product question, not just a wiring one.
- Study routes: untouched, zero files exist.
