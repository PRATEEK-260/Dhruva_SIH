# Build status

Written 2026-09-13. Read this plus `CLAUDE.md` before starting work; `IMPLEMENTATION.md`
holds the phase definitions and gates, and neither it nor `dhruva-plan.html` is
re-opened mid-build.

**One line:** phases 0–4 complete with their gates passing, phase 5 in progress —
the backend endpoints, API client, online Ask flow, and fleet list skeleton are built,
but the Boat PWA offline storage, map overlays, and voice integration are outstanding.

---

## Where things stand

| Phase | State | Gate |
|---|---|---|
| 0 — Toolchain | done | subagents load, CLAUDE.md exists, 7 plugins, real SST fetched in code |
| 1 — Skeleton | done | `docker compose up` healthy, `/health` 200, pytest green |
| 2 — Data plane | done | `conditions_at()` 5 variables from 5 datasets, **1092 ms warm** vs 3000 ms budget |
| 3 — Graph and risk | done | firewall fails CI on a fabricated number; routing 59/59 vs 92% target |
| 4 — Capsule codec | **done** | codec + audit done; codebook, TS port, QR scanning verified in tests |
| 5 — Interfaces | **in progress** | API proxy, boat Ask flow, and shore fleet list wired |
| 6 — Evaluation | not started | |

298 tests passing, ruff and pyright clean.
Repo: https://github.com/PRATEEK-260/Dhruva_SIH (public, branch `finish-phase-4`).

---

## What phase 5 still needs

1. **Boat (PWA) Offline Storage** — Service worker and Dexie integration for offline cached fields and the codebook.
2. **Shore Console Layers** — MapLibre + deck.gl overlays for SST, chlorophyll, wave height, and PFZ zones.
3. **Study Routes** — Anomaly explorer, time series, and Langfuse trace inspector.
4. **Voice Channel** — Bhashini ASR/TTS handshake and Asterisk IVR for the feature-phone path.

**Gate 5:** spoken Tamil question returns a spoken Tamil answer with a map and a tappable
evidence card, end to end.

---

## Findings that changed the plan

These were discovered by running things, not by reading docs. They are already
reflected in the code and in `CLAUDE.md`, but they are the reasoning a fresh
session would otherwise have to rediscover.

**INCOIS ERDDAP has no live data.** All 15 griddap datasets were surveyed. The
newest satellite product ends 2020-05-01 and every SST product ends 2011 or 2014.
It is registered as climatology for the phase 3 heatwave baseline, with
`coverage_end` set so `candidates()` cannot return it as a nowcast. Live data
comes from Open-Meteo and Copernicus only — four datasets, two providers.

**The plan's demo coordinate is on land.** `11.05N 79.85E` has elevation 2 m, no
maritime zone contains it, and Copernicus had to reach 17 km for a wet cell.
**Use `11.05N 79.95E`** — at sea, in EEZ and territorial waters, 51.8 nm from the
IMBL. `dhruva-plan.html` still carries the old coordinate in its evidence card
and has not been corrected.

**Providers answer with a different grid cell than you ask for.** Open-Meteo's
marine and forecast endpoints returned two different cells for one request, 11.9
and 8.2 km away. Evidence cites the cell that answered; `Observation.offset_km`
reports the distance.

**Filtering EEZ on `iso_ter1` silently loses the Andaman and Nicobar Islands** —
that record's `iso_ter1` is null, so the filter drops 664,448 km². Filter on
`sovereign1` and the total comes to 2,323,948 km², matching India's actual EEZ.

**Marine Regions publishes each maritime belt separately.** Loading only `eez`
leaves the commonest case unanswered: a boat 2 km offshore is inside the straight
baseline and falls in no zone at all.

**The PFZ bulletin URL is not publicly discoverable.** The INCOIS PFZ page is an
explainer that loads no advisory data; its only relevant outbound link is to the
Live Access Server. The scraper is built and tested but its endpoint is
configuration — it needs confirming with INCOIS. The test fixture bulletin is
**synthetic** and should be replaced with a recorded one.

---

## Known gaps, stated rather than buried

- **Risk thresholds are placeholders**, not INCOIS Ocean State Forecast criteria.
  `PROVISIONAL = True` in code, warned about in `docs/THRESHOLDS.md`. They must
  be replaced and cited before any public claim.
- **Routing accuracy is an upper bound.** `classify()`'s weights were tuned
  against the same eval set they are measured on, so 59/59 shows the layer is
  wired and measurable, not that it generalises. The fix is the Gemini 2.5 Flash
  planner the stack table specifies; swapping it in changes `classify()` alone.
- **No LLM is wired yet.** Narration is the firewall's own template, which is the
  correct failure mode but not the product. `evidence()` in `graph/build.py` is
  where the model goes.
- **`route` (node 7) and `codec` (node 9) are declared stubs** in the graph. Route
  needs the A* cost grid; codec needs joining to the encoder that now exists.
- **Eval answers have no ground truth.** `eval/queries.jsonl` has
  `expected_answer: null` throughout, because IMPLEMENTATION.md wants answers
  sourced from INCOIS or IMD bulletins and those are not in hand.
- **Bhashini credentials are empty** — `BHASHINI_USER_ID`, `BHASHINI_ULCA_API_KEY`.
  Phase 5 blocker only. Its auth is a config call that returns the real endpoint
  and key, then a compute call; build that handshake first.

---

## Running it

```bash
docker compose up -d --wait          # api, postgres, redis, caddy
docker compose --profile obs up -d   # + langfuse on :3000
```

Host ports avoid collisions with other projects on this machine: postgres
**55432**, redis **56379**, api 8000, caddy **8081**, langfuse 3000.

```bash
set -a; . ./.env; set +a
export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@localhost:55432/dhruva"
.venv/bin/python -m pytest backend/tests -q
.venv/bin/langgraph dev              # LangGraph Studio on :2024
```

`DHRUVA_DSN` is not in `.env`; the `geo` node returns empty without it.

Credentials verified working: OpenRouter, Sarvam, Copernicus Marine, NASA
Earthdata, Langfuse. Values in `.env` containing `" $ # ^` are single-quoted —
Docker Compose interpolates a bare `$`, and comments must stay on their own line.

---

## Conventions that bit us

- Commit messages: `area: imperative summary`. **No Claude co-author trailer** —
  the work ships under Prateek's name.
- `.langgraph_api/`, `.zarr_cache/`, `.env*` are gitignored. The first two are
  runtime state and were briefly committed by accident.
- Use the subagents: `erddap-explorer` for datasets, `geo-reviewer` before
  merging geospatial code, `capsule-auditor` after every codec change. The
  capsule audit found a real bug the tests missed — NaN crashed the encoder on
  every field, and clamping it to zero would have encoded a calm sea from a value
  meaning "no idea".
