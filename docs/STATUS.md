# Build status

Written 2026-09-13, updated 2026-09-28. Read this plus `CLAUDE.md` before starting work;
`IMPLEMENTATION.md` holds the phase definitions and gates, and neither it nor
`dhruva-plan.html` is re-opened mid-build.

**One line:** phases 0–4 complete with their gates passing, phase 5 in progress —
the planner now routes with Gemini, the shore console has its raster layers and a
Render + Vercel deploy exists, but Boat PWA offline storage, study routes and voice are
outstanding, and narration is still the firewall's template.

---

## Where things stand

| Phase | State | Gate |
|---|---|---|
| 0 — Toolchain | done | subagents load, CLAUDE.md exists, 7 plugins, real SST fetched in code |
| 1 — Skeleton | done | `docker compose up` healthy, `/health` 200, pytest green |
| 2 — Data plane | done | `conditions_at()` 5 variables from 5 datasets, **1092 ms warm** vs 3000 ms budget |
| 3 — Graph and risk | done | firewall fails CI on a fabricated number; routing 59/59 keyword (tuned on the set), **57/57 answered by Gemini** (never tuned on it) vs 92% target |
| 4 — Capsule codec | **done** | codec + audit done; codebook, TS port, QR scanning verified in tests |
| 5 — Interfaces | **in progress** | see below |
| 6 — Evaluation | not started | |

325 tests passing (12 skipped: no database, or live-model test not enabled), ruff and
pyright clean.
Repo: https://github.com/PRATEEK-260/Dhruva_SIH (private). Nothing since phase 3 is merged
to `main`: phase 4 and 5 work lives on `finish-phase-4` → `phase-5-demo-ui` →
`deploy-render` → `planner-model`, each built on the last.

---

## Done in phase 5 so far

- `POST /advisory`, the advisory request log (explicitly not vessel tracking), whole-table
  GeoJSON for boundaries, zones and PFZ, and the frontend API client.
- **Boat:** online Ask flow with QR handoff; boat PWA and an emulator split for the
  offline-handoff demo.
- **Shore:** boundary, INCOIS PFZ-line and fleet-list layers on real data; SST, chlorophyll and
  wave-height raster layers served by TiTiler (`/tiles` behind Caddy, COGs from
  `scripts/`); point-inspect panel; replay-aware advisory log.
- **Planner:** Gemini routes intents, keyword `classify()` is the fallback (below).
- **Deploy:** backend on Render, frontend on Vercel (`deploy/`). On 2026-09-28
  `https://dhruva-api.onrender.com/health` did not answer within 60 s — possibly a
  free-tier cold start; check before any demo.

---

## What phase 5 still needs

1. **Boat (PWA) Offline Storage** — Service worker and Dexie integration for offline cached
   fields and the codebook. No service worker or Dexie code exists yet.
2. **Study Routes** — Anomaly explorer, time series, and Langfuse trace inspector.
3. **Voice Channel** — Bhashini ASR/TTS handshake and Asterisk IVR for the feature-phone
   path. No code yet; the Bhashini key request is in progress (below).
4. **Narration by a model** — `evidence()` in `graph/build.py` still returns the firewall's
   template. The model's narration goes there, validated by the firewall.

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

**PFZ comes from the WFS behind INCOIS's own geoportal (found 2026-09-28).**
The text-bulletin URL is still not discoverable, but the public PFZ geoportal
(`incois.gov.in/geoportal/MFASPFZ/index.html`) draws its lines from two WFS
layers on INCOIS's GeoServer: `PFZ_Automation:pfzlines` (the day's lines, dated
by Year + Julian_day) and `PFZ_LandingCentres:LandingCenters_29Apr2024` (1223
centres; use names and positions only, its advisory columns are from 2024).
`python -m dhruva.sources.pfz_wfs` loads both into `pfz_line` and
`landing_centre`; the geo node finds the nearest line of the latest advisory no
more than 3 days old and within 60 nm, and fills the capsule's PFZ fields. On
28 Sep the latest advisory was 27 Sep: 66 lines, 9 off North Tamil Nadu, the
nearest 15.3 nm east of the demo point. This is an undocumented map service,
not an API — read and attributed, and its terms of use should be confirmed with
INCOIS before any public claim. Refresh it before a demo. The old
`pfz_advisory` rows (text-bulletin scraper) are a **synthetic** fixture and are
no longer served when lines exist.

**Gemini 2.5 Flash is closed to new API keys.** The Gemini API answers 404 "no longer
available to new users". `gemini-3.8-flash` answered 503 under load on 2026-09-28;
`gemini-3.5-flash-lite` answered in about 1.3 s and is the default. The free tier allows
**15 requests a minute per model** — past that every call is 429 and the planner falls
back to keywords. The live eval is paced for this (`DHRUVA_LIVE_PACE_S`, default 4.5).

**The planner now calls Gemini directly, not through OpenRouter.** The
`OPENROUTER_API_KEY` in `.env` was rejected by OpenRouter (401) and is the same length
as the Gemini key, so it was most likely that key under the wrong name. Nothing reads it
any more.

**The problem statement never asks for offline delivery.** The full SIH26176 text
("ORCA — Marine EcOsystem Reasoning with Collaborative Agents") asks for an agentic,
multi-agent conversational platform: intent, decomposition, collaborating agents,
language detection with a same-language reply, multi-turn, evidence-backed answers,
proactive alerts, geofence notifications, route optimisation. NavIC and offline do not
appear. Getting alerts to boats is already done by ISRO and INCOIS systems (DAT-SG,
NavIC Messaging Receiver, GEMINI, VCSS + Nabhmitra, SAMUDRA); none found takes a
question. ISRO's public DAT-SG ICD v1.2 defines a message addressed to one terminal
with a **23-byte** text payload — the capsule is 19 bytes, so one answer fits one
DAT-SG message. DAT-SG's only boat-to-shore packet is the distress alert, so the
question goes up over Nabhmitra (simulated); see `docs/DATSG_ICD.md`. The pitch's "every other app goes blank offshore" is false and should
not be said to ISRO judges. A repositioning draft exists but has not been adopted.

---

## Demo data — what is real and what is labelled

Added 2026-09-28 for the round-2 video. Nothing invents a reading.

- **Recorded runs** (`data/demo/recordings.json`, made by `scripts/record_demo.py`):
  real `/advisory` responses for every request the demo screens make, recorded live.
  `DHRUVA_DEMO` picks the mode: `fallback` (default: a recording answers only when
  every live source fails), `replay` (recordings first; use while filming), `off`.
  A replayed answer carries `recorded_at`, and every screen says "Replayed from a
  recorded live run of …". The script also pre-speaks each answer with Bhashini
  into `backend/.voice-cache/`, which `/voice/tts` serves first. Re-record on the
  day of filming: "tomorrow 5 AM" is matched by IST hour, so an old recording
  would replay yesterday's forecast.
- **A real past storm:** Cyclone Michaung, 4 Dec 2023, off Chennai (13.0 N,
  80.45 E). Waves from Open-Meteo marine, wind from Open-Meteo's ERA5 archive
  (registered as `open_meteo_archive`; the forecast API only reaches ~92 days
  back). Verdict NO-GO on WAVE-N3 and WIND-N3, from data alone.
- **Demo boats** (`dhruva/demo/boats.py`, `/demo/boats`): ten named positions on
  real fishing grounds, each checked to lie in India's territorial sea. Labelled
  "demo boat" everywhere; not vessels, not tracks.
- **Test inputs, unchanged:** the cyclone distance (no IMD feed yet) is always
  labelled a test input.
- Shared by the screens and the recorder, so they cannot drift:
  `frontend/src/shared/questions.json` and `demo.json`.

---

## Known gaps, stated rather than buried

- **Risk thresholds are placeholders**, not INCOIS Ocean State Forecast criteria.
  `PROVISIONAL = True` in code, warned about in `docs/THRESHOLDS.md`. They must
  be replaced and cited before any public claim.
- **Keyword routing accuracy is an upper bound.** `classify()`'s weights were tuned
  against the same eval set they are measured on. The Gemini planner was not, and
  routed 57/57 of the queries it answered; 2 of 59 timed out at the 8 s limit
  (p50 1301 ms, p95 4192 ms). Rerun with
  `cd backend && DHRUVA_LIVE_LLM=1 ../.venv/bin/python -m pytest tests/test_planner_model.py -k Live -s`.
- **The planner only picks the intent.** It does not decompose a mixed request
  ("safest route to the PFZ avoiding the cyclone") or hold multi-turn context, and the
  eight downstream nodes are plain Python, not model-driven agents. The PS asks for both.
- **The 8 s planner timeout is long.** A timed-out call adds 8 s before the keyword
  fallback answers; about 4 s would fit the latency budget better.
- **Narration is still the template.** No model writes the answer yet. `evidence()` in
  `graph/build.py` is where it goes.
- **`route` (node 7) is a declared stub.** It needs the A* cost grid. `codec` (node 9)
  now builds the capsule, but leaves PFZ and boundary-ETA fields at their defaults on
  purpose (see its docstring).
- **PS requirements with nothing behind them yet:** tides (no source; INCOIS SAMUDRA
  shows them), language detection, multi-turn, a lightning feed (the rule exists in
  `risk/rules.py`, nothing feeds it), proactive alerts, charts.
- **Eval answers have no ground truth.** `eval/queries.jsonl` has
  `expected_answer: null` throughout, because IMPLEMENTATION.md wants answers
  sourced from INCOIS or IMD bulletins and those are not in hand.
- **Bhashini credentials are empty** — `BHASHINI_USER_ID`, `BHASHINI_ULCA_API_KEY`.
  Phase 5 blocker only. A key request is in progress on the Bhashini Udyat dashboard,
  which also shows an earlier request for app "orca" as approved — check for its
  credentials first. Its auth is a config call that returns the real endpoint
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

Credentials verified working: Gemini (2026-09-28), Sarvam, Copernicus Marine, NASA
Earthdata, Langfuse (as of 2026-09-13). OpenRouter was rejected (401) on 2026-09-28
and is no longer used. `GEMINI_API_KEY` must also be set in Render's environment for
the deployed backend to use the model. Values in `.env` containing `" $ # ^` are
single-quoted — Docker Compose interpolates a bare `$`, and comments must stay on their
own line.

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
