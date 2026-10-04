# Build status

Written 2026-09-13, updated 2026-10-04. Read this plus `CLAUDE.md` before starting work;
`IMPLEMENTATION.md` holds the phase definitions and gates, and neither it nor
`dhruva-plan.html` is re-opened mid-build.

**One line:** phases 0–4 complete with their gates passing, phase 5 in progress. The
5-day upgrade plan (`DHRUVA 5-Day Upgrade Plan.pdf`, 30 Sep) is built: all 8 of the
brief's example queries answer by voice in five languages, IMD cyclone bulletins are
live, and wind and the 4 m sea limit are cited to IMD. Outstanding: Dexie offline
storage, study routes, the Asterisk IVR, model narration (still the firewall's
template), and Gate 5 recorded as a gate check.

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

502 backend tests passing (15 skipped: no database, or live-model test not enabled),
67 frontend tests passing; ruff, pyright and `tsc -b` clean (2026-10-04).
Repo: https://github.com/PRATEEK-260/Dhruva_SIH (private; checked with `gh` on
2026-10-03). Its **default branch on GitHub is `round2-demo`**, which is why the
scheduled `keep-render-awake` workflow runs from it. Nothing since phase 3 is merged to
`main` (79 commits behind `round2-demo`): phase 4 and 5 work lives on `finish-phase-4` →
`phase-5-demo-ui` → `deploy-render` → `planner-model` → `round2-demo`, each built on
the last.

---

## The 5-day upgrade plan (3–4 Oct)

| Upgrade | Commit | What |
|---|---|---|
| 1 Query #7, why fish declined | `efdde20` | last 30 days vs the same weeks in 10 earlier years (GlobColour MY, OSTIA NRT/REP); worked example off Veraval in `demo-assets/decline_example_veraval.txt` (chlorophyll 1.55 vs usual 2.77, flagged down) |
| 2 Live IMD bulletins | `516bed2`, `7618999` | National Bulletin archive read every 30 min, PDF parser, 300 km override, unreadable → CAUTION with link |
| 3 Remaining brief queries | `6904594` | zones to avoid, alerts (+ thunderstorm forecast, TSTORM-C1), tides, high-chlorophyll water, straight-line route |
| 4 Cited limits | `5fda4ae` | IMD Marine Weather Services SOP 7.1: wind 20 / 24.3 kt and the 4.0 m sea for every class; small-boat wave limits provisional |
| 5 Polish | `bbd9f25` | phone UI in ta/ml/or/hi, no figures in the spoken verdict, Blocked/Unsafe repeat until "I understand", last answer on the home screen |

Every new answer is rule-picked sentences in `data/phrases/*.json` (Bhashini via
`scripts/phrases.py`), every number an evidence row, firewall-checked in the language
asked; the firewall now reads a clock time ("06:40") as one number. Machine
translation errors found and fixed by hand, all listed in each file's `_about`:
weather "Depression" rendered as the illness in all four languages; Hindi/Odia
article "एक"/"ଏକ" (also "one") read as a number; dropped negations; "to the east"
read as a range. **Every Indic line still needs a native speaker's check.**

## Done in phase 5 so far

- `POST /advisory`, the advisory request log (explicitly not vessel tracking), whole-table
  GeoJSON for boundaries, zones and PFZ, and the frontend API client.
- **Boat phone (`/boat`):** ask by voice or text, QR scan handoff. The headline is the
  action ("Do not go to sea.") with one reason taken from the capsule's own hazard flags,
  so it works offline; no number on the main verdict. Evidence rows, the number check and
  the nine-agent trace sit behind **Show evidence**. A Leaving selector alone sets the
  departure time (no question names a time). Every distance is in nautical miles; a
  figure the source gave in km keeps it beneath ("given as 180 km").
- **Voice (Bhashini):** `POST /voice/tts` and `/voice/asr` (`api/voice.py`,
  `lang/bhashini.py`) use `BHASHINI_INFERENCE_API_KEY` and `BHASHINI_PIPELINE_ID`.
  The phone records, converts to 16 kHz mono WAV and transcribes; answers are spoken
  through a fallback chain: Bhashini live → the clip saved in Cache Storage → the
  verdict clip shipped in `public/voice/{ta,ml,or,hi}/` → the phone's own speech engine,
  and the screen names which one played. Spoken sentences are cached on disk in
  `backend/.voice-cache/` so a repeat plays when Bhashini answers 504. The TTS language
  is held to a 2–3 letter code so it cannot steer the cache path.
- **Service worker (`frontend/public/sw.js`, production builds only):** pages and assets
  network-first with cache fallback, voice clips and fonts cache-first, `/api` never
  cached. The phone opens, decodes and speaks with its radio off after one online visit.
- **Channel (`frontend/src/shared/channel/`):** a `Channel` interface. Nabhmitra (VCSS) is
  the target and carries the one-byte question up; its format is not public, so its
  adapter is a placeholder. DAT-SG builds the answer as a real message 41 frame (ICD
  v1.2 Table 8, text control word 0x3, 23 base-85 characters), parsed back in tests
  over the 500-capsule corpus. No other code names a channel.
- **Boat terminal (`/emulator`):** draws the 220-bit DAT-SG frame and asks about now.
- **Shore:** boundary, INCOIS PFZ-line and fleet-list layers on real data; SST, chlorophyll and
  wave-height raster layers served by TiTiler (`/tiles` behind Caddy, COGs from
  `scripts/`); point-inspect panel; replay-aware advisory log. **Warn boats** places a
  cyclone either from IMD's bulletin (Michaung, judged on that hour's archived sea: 5 demo
  boats Blocked at 87–219 km, 5 Safe at 302 km and beyond) or by hand as a labelled test
  input, and shows what each boat will hear.
- **Planner:** Gemini routes intents, keyword `classify()` is the fallback (below).
- **Query #7, "why are there fewer fish here?" (3 Oct, 5-day plan upgrade 1):**
  `analytics/decline.py` compares the last 30 days in a ~20 x 20 km box with the
  same weeks in the 10 earlier years; a change is unusual only past the
  year-to-year spread, and fewer than 2 years with data is No data. Rule-picked
  sentences in en/ta/ml/or/hi (`data/phrases/decline.json`, Indic by Bhashini via
  `scripts/decline_phrases.py`; 6 lines hand-fixed, listed in the file's `_about`,
  awaiting a native speaker), every number an evidence row, firewall-checked in
  the asked language. NO-GO replaces the fishing-zone line. Data
  (`analytics/baseline.py`, measured 3 Oct): chlorophyll from the multi-year
  GlobColour L4 gap-free product for every window (it runs to 8 days before
  today; NRT keeps only 17 days); SST from OSTIA NRT for the current window and
  OSTIA REP for the baseline (they agree to 0.04-0.06 C). Cold first call ~38 s,
  then cached in process for the day; Render's boot warm-up asks it once. Online
  only: the chip is hidden on the terminal and offline. Off the demo point on 3
  Oct chlorophyll was the highest in 11 years (2.87 vs usual 1.49 mg m-3).
- **Risk hardening (29 Sep):** plausibility bounds at the fetch layer
  (`sources/plausibility.py`) drop readings that cannot be true in Indian waters (SST
  outside 15–35 °C, waves outside 0–20 m, wind over 150 kt…); the next source answers, or
  the variable goes missing and the rules say UNKNOWN. The bounds are physical, so a
  32.8 °C heatwave reading still counts. Default-deny: an unrecognised alert type, or a
  cyclone or lightning alert with no position, fires ALERT-C0 and forces at least
  CAUTION. `POST /advisory` takes `test_alerts` as a labelled test input.
- **Live IMD bulletins (3 Oct, 5-day plan upgrade 2):** IMD has no API.
  `sources/imd_feed.py` reads RSMC New Delhi's National Bulletin archive page
  (`archive-information.php?internal_menu=MQ==&menu_id=NA==`, newest 30, POST
  `search_year` for older), downloads new PDFs with their SHA-256 into
  `data/imd/national/` and records them in `data/imd/feed.json` (both gitignored,
  runtime) with when the list was checked; Render runs it at boot and every 30 min.
  `sources/imd_parser.py` (pypdf) reads number, system id, category, name, issue
  time, centre, forecast track, fishermen warning and next-issue time; tested on 7
  real bulletins. `imd_bulletin.live_status()` applies the newest bulletin of each
  system while in force (until the next is due + 3 h): Depression and above in the
  boat's basin gives the cyclone distance from the track point nearest the hour asked
  (300 km override); an unreadable bulletin, or a far one whose fishermen warning
  names the boat's coast, adds an alert that forces CAUTION, with the link. With none
  in force the answer says "No active IMD cyclone bulletin as of <check time>".
  `POST /advisory` returns it as `imd`; `GET /imd/status` serves the shore console.
  On 3 Oct nothing was in force (BOB/07/2026 became a low on 30 Sep).
  Judgement calls to know: depressions trigger the same 300 km override as cyclones
  (IMD advises fishermen not to venture for them too), and coast matching is a
  keyword table in `imd_bulletin._COASTS` that can only add caution.
  National Bulletin No. 29 (BOB/06/2026) has no extractable body text: that is the
  real case the unreadable path exists for.
- **Michaung replay:** now IMD National Bulletin No. 19 (BOB/06/2023, 0845 IST 4 Dec
  2023), `bulletin: "michaung_nb19"`, read from its PDF by the same parser (centre
  13.2N 81.2E at 0000 UTC, unchanged). The old RSMC advisory record is gone, so
  recordings keyed on `rsmc_michaung_adv9` no longer replay: re-record.
- **Deploy:** backend on Render (one container: Postgres with the boundaries, PFZ lines and
  landing centres baked into the image, Redis, Caddy, TiTiler and the API, warmed and
  log-seeded at boot by `deploy/render/start.sh`); frontend on Vercel, built from git with
  the repo-root `vercel.json`, which rewrites `/api` and `/tiles` to Render. On 2026-10-03
  `https://dhruva-api.onrender.com/health` answered 200 in 0.4 s. Render's free tier
  sleeps after 15 minutes idle; `.github/workflows/keep-render-awake.yml` pings it. Still
  check before any demo.

---

## What phase 5 still needs

1. **Dexie offline storage** — the service worker caches the app and the voice clips, but
   nothing stores received capsules or cached fields in IndexedDB yet. No Dexie code
   exists and it is not a dependency.
2. **Study Routes** — Anomaly explorer, time series, and Langfuse trace inspector.
3. **Asterisk IVR** — the feature-phone voice path. No code yet. (Bhashini voice on the
   phone is done, above.)
4. **Narration by a model** — `evidence()` in `graph/build.py` still returns the firewall's
   template. The model's narration goes there, validated by the firewall.

**Gate 5:** spoken Tamil question returns a spoken Tamil answer with a map and a tappable
evidence card, end to end. Every piece now exists on `/boat` (voice in, Bhashini Tamil
voice out, PFZ map, Show evidence), but the gate has not been run end to end through
Bhashini and recorded. The one recorded round-trip, `demo-assets/voice_roundtrip.txt`
(28 Sep), used Sarvam as a stand-in, before Bhashini was wired.

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
with a **23-byte** text payload. The capsule goes as 23 base-85 characters in that text
message, framed byte for byte by `frontend/src/shared/channel/datsg.ts`. DAT-SG's only boat-to-shore packet is the distress alert, so the
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
  day of filming: the go/no-go question is recorded at every Leaving option and a
  departure is matched by IST hour, so an old recording would replay yesterday's
  forecast.
- **A real past storm:** Cyclone Michaung, 4 Dec 2023, off Chennai (13.0 N,
  80.45 E). Waves from Open-Meteo marine, wind from Open-Meteo's ERA5 archive
  (registered as `open_meteo_archive`; the forecast API only reaches ~92 days
  back). Verdict NO-GO on WAVE-N3 and WIND-N3, from data alone.
- **Demo boats** (`dhruva/demo/boats.py`, `/demo/boats`): ten named positions on
  real fishing grounds, each checked to lie in India's territorial sea. Labelled
  "demo boat" everywhere; not vessels, not tracks.
- **Cyclone position:** live answers use IMD's bulletins in force; the Michaung
  replay reads IMD's own bulletin through the parser. A hand-placed cyclone (Warn
  boats' demo position, the terminal's "Simulate a cyclone warning") is always
  labelled a test input; so are `test_alerts`. The plan wanted the hand-placed control
  on the shore console only, but the final video script uses the terminal's button,
  so it stays there, relabelled.
- Shared by the screens and the recorder, so they cannot drift:
  `frontend/src/shared/questions.json` and `demo.json`.

---

## Known gaps, stated rather than buried

- **Risk thresholds are partly cited.** Wind (20 / 24.3 kt) and the 4.0 m sea come
  from IMD's Marine Weather Services SOP 7.1 (`docs/THRESHOLDS.md`); the stricter
  small-boat wave limits are provisional, and the evidence card says which a verdict
  used. The productive-water SST range (26–30 °C) is provisional too.
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
- **`route` (node 7) is a straight-line check, not a planner.** Waves at 8 points to
  the nearest INCOIS zone against the boat's limit; A* over a cost grid is future
  work. `codec` (node 9)
  builds the capsule with PFZ bearing, distance and freshness from the nearest INCOIS
  line, but leaves boundary distance, type and ETA at their defaults on purpose until
  drift projection exists (see its docstring). `chl_class` also stays at its default:
  no classifier exists.
- **PS requirements with nothing behind them yet:** language detection, multi-turn,
  a lightning *observation* feed (thunderstorms are forecast-only, from Open-Meteo
  weather codes), proactive alerts, charts. Tides come from Open-Meteo's marine
  model, labelled "not for navigation".
- **Depressions trigger the 300 km override** like cyclones (IMD SOP 7.1(iv) warns
  fishermen for them too); the phone's reason line still says "cyclone warning".
- **IMD warning areas are not mapped.** Coast matching is a keyword table
  (`imd_bulletin._COASTS`) that can only add CAUTION.
- **Eval answers have no ground truth.** `eval/queries.jsonl` has
  `expected_answer: null` throughout, because IMPLEMENTATION.md wants answers
  sourced from INCOIS or IMD bulletins and those are not in hand.
- **Bhashini runs on a fixed inference pipeline, not the ULCA handshake.** Voice uses
  `BHASHINI_INFERENCE_API_KEY` and `BHASHINI_PIPELINE_ID` (both set in `.env`).
  `BHASHINI_USER_ID` and `BHASHINI_ULCA_API_KEY` are still empty and nothing reads them,
  so the config-then-compute handshake CLAUDE.md describes is not built. Bhashini
  translation runs only ahead of time (`scripts/verdict_labels.py` writes the verdict
  labels and reasons); nothing translates at request time, and Indic answers come from
  the shipped codebook.

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
and is no longer used. Bhashini's inference key generated the shipped clips and the
voice cache on 28–29 Sep; not re-checked live since. `GEMINI_API_KEY`,
`BHASHINI_INFERENCE_API_KEY` and `BHASHINI_PIPELINE_ID` must also be set in Render's
environment for the deployed backend to use the model and live voice. Values in `.env` containing `" $ # ^` are
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
