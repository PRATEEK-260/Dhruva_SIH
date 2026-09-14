# DHRUVA — combined reference

Generated 2026-09-14, merging three source documents for one-file reading
convenience. **The three originals stay authoritative** — this file is a reading copy,
not a new editable source of truth. Per CLAUDE.md: `dhruva-plan.html` and
`IMPLEMENTATION.md` are build-contract documents that are not re-opened mid-build; if
you're here to change a decision, edit the original and say why, don't edit this copy.

- **Part 1 — Context & judge Q&A** (from `context.md`): fast orientation, the settled
  architecture decisions, and ready answers to the questions judges actually ask.
- **Part 2 — Build plan** (from `dhruva-plan.html`, converted from its original styled
  HTML — some layout/diagram elements do not survive the conversion to markdown): the
  pitch, the five differentiating decisions, the graph, the capsule, the risk table, the
  eight-minute demo script.
- **Part 3 — Implementation contract** (from `IMPLEMENTATION.md`): phase-by-phase build
  instructions and gates.

---

# Part 1 — Context & Judge Q&A

Deep-sea Hazard, Routing & Understanding via Vernacular Agents. ISRO PS 26176 (ORCA).

This file is a fast orientation doc — what the project is, why it's built this way, and how
to answer the questions judges actually ask. For anything that changes as the build moves
(what's done, what's outstanding, test counts), read `docs/STATUS.md` instead of this file —
multiple sessions are actively building on this repo and STATUS.md is what's kept current.
`CLAUDE.md` is the full, authoritative project instructions file; this is a shorter derivative
of it plus material from conversation, not a replacement.

---

## The thesis, in one paragraph

Reasoning runs onshore, answers survive offshore. A full marine safety advisory — go/no-go
verdict, sea state, nearest fishing zone, boundary distance, why — compresses to **145 bits**,
small enough to fit inside a single 220-bit NavIC L5 message segment. A phone with zero
connectivity reconstructs a full spoken advisory, in a regional language, from those 145 bits
and a codebook shipped with the app at install time. No network, no cell tower, no signal
needed at the point of use.

## Why it's built this way — the two hard constraints

**No hardware, no transmission.** The NavIC uplink belongs to ISRO; no team gets to broadcast
on it. The project's claim is *segment conformance* — the 145-bit packet is provably, checkably
correct against ISRO's real 220-bit field format — not that this team has built or demonstrated
actual satellite transmission. Real delivery to open ocean would ride NavIC's own broadcast
once ISRO enables it; that's the piece nobody outside ISRO can build or demo.

**The LLM never emits a number.** Every figure that reaches a screen or a spoken sentence came
from a tool, not a model. An `EvidenceBundle` carries `{key, value, unit, dataset_id, cell,
valid_time}` for every number; narration is generated, then every numeric token in it — ASCII
digits, Indic digits, spelled-out numerals — is checked against the bundle. A number with no
evidence cannot render anywhere, including the shore console. This is the entire trust story.

## Other settled decisions (see CLAUDE.md for the full list)

- PFZ (fishing zone) data is **scraped**, not an API — always attributed with `source_url` and
  `fetched_at`, never presented as if a live feed exists.
- Boundary lines (EEZ/IMBL/MPA) are **indicative**, never legal — every rendered line carries
  that flag, and now (Shore Console) a visible dashed style and legend, not just a JSON property.
- Risk thresholds (`docs/THRESHOLDS.md`) are **engineering placeholders**, not yet validated
  against INCOIS's own Ocean State Forecast criteria — stated plainly, never presented as official.
- Absolute overrides beat everything: a cyclone warning within 300 km, lightning within 50 km,
  or any tsunami alert forces NO-GO regardless of what the computed wave/wind verdict says.
  A favourable fishing zone never renders above an active hazard.

## Stack, locked

LangGraph + Pydantic v2 orchestration · Gemini 2.5 Flash for planning (not yet wired — narration
is currently the firewall's own template) · Sarvam/Bhashini for voice (not yet wired) · FastAPI +
PostgreSQL/PostGIS backend · React + MapLibre frontend, two surfaces (Boat PWA, Shore Console) ·
QR / Bluetooth / SMS as the three transports the team controls for demoing the wire format,
distinct from NavIC itself.

---

## Judge Q&A — questions this project invites, and how to answer them

### "How does the 145-bit signal actually transmit and get received?"

It doesn't, by this team — and it isn't supposed to. The NavIC uplink is ISRO's alone; no team
gets spectrum access to it. What's actually proven is **segment conformance**: the 145-bit
capsule is built to fit exactly inside NavIC's real 220-bit L5 message format, checkable against
the field table on paper. The identical wire format also runs over QR, Bluetooth and SMS —
transports the team can actually build without hardware — which is what the demo uses to prove
the *decode* side works with zero connectivity. The moment ISRO puts this on their own broadcast,
every NavIC receiver in the Indian Ocean gets it, with no new infrastructure required.

### "So how does a QR code reach a fisherman in the middle of the ocean?"

It doesn't, by itself — a QR is a printed or displayed image; nothing about it transmits. It's
scanned at a landing centre or hub before the boat leaves shore (INCOIS already operates 586 of
these for PFZ bulletins), cached on the phone, then decoded fully offline once at sea — the exact
mechanism the demo shows. The genuine open-ocean, no-relay leg is NavIC's job, since satellite
broadcast already reaches anywhere with sky view. That's precisely the leg this team is honest
about not having built — the whole "segment conformance, not transmission" framing exists to
name that gap rather than paper over it.

### "Every output says 'advisory only, follow official INCOIS and IMD warnings' — why?"

Because DHRUVA computes a decision-support layer, not an authoritative warning. Concretely:
the risk thresholds are engineering placeholders, not yet validated against INCOIS's own
published criteria; PFZ data is scraped and could lag the real bulletin; boundary lines are
indicative, not surveyed legal lines. If DHRUVA were ever wrong and someone acted on it as if
it were official, that's a real safety failure. The notice is baked in redundantly at multiple
layers on purpose, so it's mechanically impossible to ship an advisory without it.

### "So are you just relaying their guidelines?"

No. INCOIS/IMD don't compute a personalized go/no-go for a specific boat class at a specific
lat/lon in real time — DHRUVA fuses wave height, wind, currents, SST, chlorophyll and boundary
proximity from half a dozen live sources and runs its own deterministic threshold engine to
produce that verdict. Then it delivers the result somewhere their own channels don't reach: a
phone with its radio fully off, speaking a regional language, from 145 bits. The disclaimer
reflects one specific fact about DHRUVA's own logic — an official cyclone/tsunami/lightning
warning is an absolute override above everything DHRUVA computes itself — not an admission that
the system does nothing on its own.

---

# Part 2 — Build Plan

ISRO · PS 26176 · ORCA · Final plan

Deep-sea Hazard, Routing & Understanding via Vernacular Agents

A marine decision-support system whose reasoning runs onshore and whose answers survive offshore — the full advisory compresses to 145 bits, one NavIC broadcast segment, and the phone reconstructs the explanation in the fisherman's language with no network.

Locked 12 Sep 2026 Orchestration LangGraph Backend Python 3.12 / FastAPI Frontend React + MapLibre + deck.gl Deploy Docker on Oracle A1, Mumbai

One day, from the deck

## What this is, told the way the user lives it

Every design decision further down this page answers to these four moments. If a feature does not show up here, it is not in scope. Open the pitch with this, not with the architecture diagram.

04:40ASHORE

A fisherman in Nagapattinam asks his phone, out loud, in Tamil, whether he can go out this morning. He does not type and he does not read. The phone answers in Tamil — go, but be back by four — and shows one card: waves 2.5 m, wind 18 knots, the fishing zone 12 nautical miles to the southwest. "இன்று காலை கடலுக்குப் போகலாமா?"

07:1520 KM OUT

His signal dies. This is where every other app of this kind goes blank. His does not: before he left, the system sent a message small enough to ride ISRO's NavIC satellite signal, the channel that already reaches boats with no mobile network, and his phone kept it. He can still ask, still hear the answer, still see the zone.

09:20DRIFTING

The current pushes him east. The phone speaks without being asked: at this heading you cross the Sri Lanka maritime line in 34 minutes, turn to 090. That sentence is the difference between an ordinary day and a seized boat with the crew in custody.

ANY TIMEDOUBT

When he doubts the advice, he taps the number. It names the satellite dataset it came from, the patch of sea it describes, and the hour it is valid for. The system cannot invent a wave height — it can only report one it actually fetched.

The wedge

## What every other team will build, and what we build instead

The default reading of this problem statement is a cloud chatbot over ocean APIs with a map. Roughly every team will submit that, and it stops working 15 km offshore, which is where the user actually is. Five decisions separate us, each of them demonstrable in 90 seconds.

Offline

### Reasoning onshore, answers offshore

Agents run on a server; their conclusion is encoded into a 145-bit capsule that fits one NavIC L5 segment (220 bits, 12 s broadcast). The app expands it offline into full regional-language narration from a shipped codebook.

Trust

### Numeric firewall

The LLM never emits a number. Every figure is computed in Python from a cited grid cell, and a validator rejects any digit in the narration that is absent from the tool results. Hallucinated wave heights become structurally impossible, not merely unlikely.

Safety

### Predictive boundary ETA

Not "you crossed the IMBL" but "at your present heading plus 0.8 kt of set, you reach the line in 34 minutes." Drift-projected, carried as an 8-bit field inside the capsule, so it still fires with the network down.

Science

### Attribution, not adjectives

"Why has productivity declined here" is answered with a marine-heatwave detection (Hobday: 5+ days above the seasonal 90th percentile) and a chlorophyll anomaly series, with the method named in the answer.

Access

### Voice first, feature phone included

Bhashini ASR and TTS over an IVR number, so the system works for a user with no smartphone and no reading. Text chat is the fallback, not the product.

Loop

### Catch reports score the PFZ

Returning boats log catch against the zone they were advised toward. That gives a rolling skill score per zone — a measured accuracy number in the demo, which no static advisory app can show.

Architecture

## One graph, ten nodes, deterministic where it counts

LangGraph holds the state machine. Language handling wraps the whole graph; retrieval and computation are ordinary Python tools; the LLM plans, selects tools and narrates, and nothing else. Every run emits an evidence bundle that the UI renders and the codec compresses.

0

### Planner

Classifies intent, detects language, decomposes into a tool plan with a token and latency budget, routes to the parallel branch.

LangGraph router · Gemini 2.5 Flash

1

### Language

Speech to text in, translation both ways, speech out. Wraps the graph rather than sitting inside it, so every downstream node works in English.

Bhashini ULCA pipeline · IndicTrans2 fallback

2

### Data discovery

Given variable, bounding box and time, picks the source and returns dataset IDs plus fetch URLs. Registry-driven, so a new dataset is a YAML entry, not code.

ERDDAP griddap · Copernicus · Open-Meteo

3

### Ocean analytics

SST fronts, chlorophyll gradients, PFZ proxy zones, anomaly series, marine heatwave detection. Pure array computation, no model in the loop.

xarray · dask · Zarr cache

4

### Weather intelligence

Wind, significant wave height, swell period, squall and lightning risk, cyclone track proximity, for now plus 72 hours.

Open-Meteo Marine · IMD bulletins

5

### Geospatial reasoning

Distance to IMBL, EEZ, marine protected areas and closed zones; drift-projected crossing ETA from heading, speed and surface current.

PostGIS · marineregions EEZ · shapely

6

### Risk engine

Deterministic thresholds → SAFE / CAUTION / NO-GO with the rule that fired. Boat class changes the thresholds: a 9 m FRP boat is not a 24 m trawler.

Rule table from INCOIS OSF criteria

7

### Route

Least-cost path over a wave, wind and current cost grid with a no-go mask, returning waypoints and a fuel proxy — a solver, not a prompt.

A* over 0.05° grid · isochrones

8

### Evidence

Builds the card behind every claim: value, dataset ID, timestamp, grid cell, threshold crossed. This is what the numeric firewall validates against.

Pydantic schema · Langfuse trace

9

### Capsule codec

Encodes the decision to 145 bits, picks the reason code, and hands it to whichever channel is reachable. The offline expander is the same codebook in reverse.

bitstruct · 256-entry reason codebook

Signature mechanism

## The 145-bit advisory capsule

ISRO's own signal-in-space ICD for INCOIS messages carries advisories on NavIC L5 at 1176.45 MHz in 220-bit segments, up to ten segments per message, 12 to 120 seconds of broadcast. Message ID 20 carries PFZ, ID 21 carries high-wave, cyclone, tsunami and all-clear warnings. That constraint is the design brief nobody else will read: if an answer cannot fit in a segment, it cannot reach a boat that has no cellular signal.

| Field | Encoding | Bits |
|---|---|---|
| Message type + schema | enum | 7 |
| Issue time | 15-min slot, 7-day wrap | 10 |
| Validity | hours, 0–15 | 4 |
| Zone cell + fine offset | 0.05° grid over Indian EEZ | 36 |
| Risk class | safe / caution / no-go | 2 |
| Hazard flags | bitmap: wave, wind, squall, lightning, cyclone, current, fog, tsunami | 8 |
| Wave Hs | 0–7.75 m @ 0.25 m | 5 |
| Wind speed + direction | 0–63 kt, 16-point | 10 |
| Current speed + set | 0–3.1 kt, 16-point | 9 |
| SST | 18–33.5 °C @ 0.5 °C | 5 |
| Chlorophyll class | 4 levels | 2 |
| PFZ bearing, distance, confidence | 16-point, 0–63 nm | 12 |
| Boundary distance + type | 0–31 nm; IMBL / MPA / closed | 7 |
| Boundary ETA | 0–255 min, drift-projected | 8 |
| Reason code | codebook index, 256 templates | 8 |
| Evidence hash | truncated, for audit | 12 |

### Bit budget

Payload145 bits

NavIC segment220 bits

Headroom75 bits

The 8-bit reason code is the trick. The server decides why; the phone stores 256 explanation templates in 12 languages and renders the sentence locally. A full spoken Tamil advisory costs the link one index, not a paragraph.

Headroom holds a 4-waypoint return route at reduced precision when the risk class is NO-GO.

We do not need the satellite to prove the satellite claim, and we are not buying hardware to fake it. The NavIC uplink is ISRO's, so no team in this competition gets to transmit on it. That means the demonstrable claim was never "we broadcast" — it is "our advisory fits the segment ISRO already broadcasts on." That is arithmetic, and arithmetic is checkable on a table in front of a judge. We carry the identical 145-bit wire format over three transports we control: a QR code (19 bytes, base32 for scanner reliability), Bluetooth between two phones, and SMS. Same bits, same decoder, same spoken sentence, no purchase order and no lead time.

### Bonus track, only if the hardware is free

GNSS-SDR has published performance figures for IRNSS L5 on a low-cost RF front end (NAVIGATION, Vol 70 No 2), and an archived RTL-SDR NavIC receiver already does acquisition, tracking and subframe extraction at 1176.45 MHz. Neither decodes INCOIS message IDs 20 and 21 — that layer does not exist in open source, and publishing one would be a first.

We are not buying an SDR to find out. One person files a loan request with the MAIT communications lab for an RTL-SDR or USRP in week one; if a unit turns up, the message-ID-20/21 decoder is a weekend of work on top of an existing tracking loop, with a hard abandon date at D13. If none turns up, nothing on the critical path notices. Free hardware is worth asking for; paid hardware is not worth the schedule risk.

### Offline envelope — state it before you are asked

With no network the app answers from the last capsule plus cached fields and the phone's own GPS. That covers the verdict, the numbers in the capsule, the PFZ bearing, boundary ETA against live position, and route replay. It does not cover a new free-form question about a region that was never fetched. Say this in the demo; a judge who finds the edge you hid trusts nothing else you claimed.

Offline figures are quantised, not rounded for display: wave to 0.25 m, SST to 0.5 °C, current to 0.1 kt, every bearing to the 16-point compass. Pick demo values that sit on the grid and the online card and the decoded card agree to the digit — otherwise a judge watches the wave height change when you switch off the radio.

Broadcast is the scaling story. One capsule per zone serves every boat in that zone, so cost grows with the number of zones, not the number of users. A chatbot costs one inference per question per user; this costs one encode per zone per cycle.

Interface

## Three surfaces over one graph

The design constraint is not a screen size, it is a wet deck at 11am with the sun overhead, one hand on the tiller and possibly no reading. That rules out a chat transcript as the primary surface. The conversation is the input; a single decision card is the output, and the map is where the decision is checked, not where it is read.

**Glare** — Contrast floor of 7:1, no grey-on-grey, no thin weights below 15 px.

**Wet hands** — Touch targets 56 px minimum, no long-press, no drag-only controls.

**Literacy** — Colour, icon, and spoken audio carry the verdict together. Colour is never alone.

**Link** — Every screen states its data age and whether it came from network or capsule.

**Battery** — Map tiles capped to the cached coastal window; no continuous GPS polling.

OFFLINE · CAPSULE 14 MIN OLD தமிழ்

CAUTION

Go, but return before 16:00

எச்சரிக்கை — மாலை 4 மணிக்கு முன் திரும்பவும்

Wave

2.5 m

Wind

18 kt NW

Set

0.8 kt

Fishing zone225° SW · 12 nm

CONF 2/3

IMBL at present heading34 min

TURN 090°

Listen

Show route

Surface 1 — fisherman, PWA, shown here in its offline state

### Every number opens its evidence

Value

2.5 m significant wave height

Dataset

open_meteo_marine · wave_height

Cell

11.05°N, 79.85°E · 0.05° grid

Valid

2026-09-13 06:00 IST · +18 h forecast

Rule

WAVE-C2 · caution ≥ 2.0 m for FRP < 12 m

Tapping the figure in the card opens this. It is the same bundle the numeric firewall validated against, so the UI cannot show a number the system cannot source.

### Capsule inspector

hdr zone 36 risk fields 43 bnd why 75 free

A judge-facing panel that shows the actual 145 bits, which field each run occupies, and the sentence the codebook expanded them into. The mechanism is invisible by design, so the UI has to make it visible once.

Surface 2 — shore console for coastal authority and disaster management: fleet state, breach watch, layered map, and a composer that shows the payload cost before it broadcasts

| Surface | User | Screens | Built in |
|---|---|---|---|
| Boat | Fisherman, crew | verdict card · voice ask · PFZ compass · route · boundary countdown · capsule history | PWA, offline-first, 12 languages |
| Shore | Coastal authority, disaster management, operators | fleet map · breach watch · zone layers · broadcast composer · advisory log | desktop React + MapLibre + deck.gl |
| Study | Researcher, INCOIS analyst | anomaly explorer · time series · marine heatwave view · trace inspector · dataset registry | same app, analysis routes |

01

Verdict before detail. The first thing on screen is GO, CAUTION or NO-GO with a plain-language instruction. Numbers sit below it; the chat transcript sits below that.

02

Every figure is tappable and opens its evidence card. A number with no source cannot be rendered — the component requires the bundle.

03

Answers are map cards, not paragraphs. A location question renders a map with the answer drawn on it, plus one sentence and one spoken line.

04

Data age is always visible. Network, capsule or stale, with minutes since issue, on every surface including the console.

05

NO-GO outranks everything. A favourable fishing zone never renders above an active hazard, and the route view refuses to draw a path through a no-go mask.

Stack

## Locked choices

| Layer | Choice | Why this, over the obvious alternative |
|---|---|---|
| Orchestration | LangGraph 0.2 + Pydantic v2 | Explicit state, checkpointing and cyclic re-planning. CrewAI's role-play abstraction hides exactly the control we need to demo. |
| Model — planning | Gemini 2.5 Flash via OpenRouter | Cheap and fast for tool selection and decomposition, where the reasoning is structural rather than linguistic. |
| Model — Indic | Sarvam-30B (API) · Sarvam-105B open weights | Trained for 22 Indian languages, Apache 2.0, Indian-hosted. An ISRO panel reads a sovereign model in the stack as an argument, not a detail. Qwen3-8B on Ollama remains the offline path. |
| Backend | Python 3.12 · FastAPI · arq | Async tool fan-out and scheduled ingests without dragging in Celery's broker weight. |
| Array compute | xarray · dask · Zarr cache | NetCDF and OPeNDAP are the native formats of every ocean source. Zarr caching of subsets is what gets a query under 6 s. |
| Database | PostgreSQL 16 · PostGIS · pgvector · TimescaleDB | One engine for geofencing, advisory RAG and vessel tracks. A separate vector DB would be a fourth service for no gain. |
| Tiles | TiTiler (raster) · pg_tileserv (vector) | Serve COGs and PostGIS layers directly; no pre-rendering step in a 3-week build. |
| Frontend | React 19 · Vite · TypeScript · MapLibre GL · deck.gl | MapLibre over Mapbox: no token, no quota, no cost surprise in front of judges. deck.gl for the grid and track layers. |
| Offline | PWA · service worker · Dexie (IndexedDB) | Capsule store, codebook and last-known fields survive airplane mode. A native app would cost a week we do not have. |
| Language | Bhashini ULCA primary · Sarvam Saarika ASR and Bulbul v3 TTS as the quality path | Bhashini is free and government-run, which is the right default. Sarvam's speech models are the fallback when Bhashini rate-limits, and the better voice for the recorded demo. |
| Voice channel | Asterisk IVR + WhatsApp Cloud API | Reaches a feature phone. The chat UI alone excludes a large share of the actual user base. |
| Observability | Langfuse, self-hosted | Traces double as the explainability record. The judge-facing "show your reasoning" panel is a Langfuse trace, rendered. |
| Infra | Docker Compose · Oracle A1 (2 OCPU / 12 GB, Mumbai) · Caddy | Already running, free tier, Mumbai region keeps latency to INCOIS and users low. |

Data

## Sources, access, and the traps in each

| Source | Gives | Access | Trap |
|---|---|---|---|
| INCOIS ERDDAP | Oceansat-2 OCM ocean colour, Indian Ocean grids | griddap REST → JSON / CSV / NetCDF, no key | TLS chain fails verification from some hosts — pin the CA bundle, do not disable verification. |
| Copernicus Marine | SST, chlorophyll, currents, waves, global | copernicusmarine Python toolbox, free account | Registration approval is not instant — do it on day 1, not day 12. |
| Open-Meteo Marine | Wave height, swell, wind, forecast + ERA5 archive | REST, no key | Model resolution is coarse near shore; label it as forecast, not observation. |
| MOSDAC (ISRO) | INSAT-3D/3DR imagery, cyclone products | registered download, ordered products | Bulk ordering is slow. Cache a fixed demo window locally. |
| INCOIS PFZ advisory | Official daily PFZ lines, 586 landing centres | HTML / text bulletins — no API | Must be scraped and attributed. Say so in the architecture diagram rather than implying a feed. |
| NASA PACE OCI | Hyperspectral ocean colour — phytoplankton community, not just chlorophyll concentration | OB.DAAC · earthaccess Python | Enrichment only. It sharpens the decline-attribution answer; never let the core path depend on it. |
| Marine Regions (VLIZ) | EEZ, IMBL, MPA polygons | shapefile download → PostGIS | Indicative boundaries. Label them as such in the UI; never render as a legal line. |
| GEBCO | Bathymetry for depth and shelf context | grid download | Large file; subset to the Indian EEZ once and store as COG. |
| Bhashini | ASR, translation, TTS for 22 languages | two-step config then compute call | Auth is a config call that returns the real endpoint and key — build that handshake first, it surprises people. |

Sequence

## Build phases

Twenty-one working days, sized so that the offline demo exists by the halfway point. Compress or stretch proportionally to your actual deadline, but keep the order: the capsule is the differentiator and it must not be the thing that runs out of time.

D1–D2

### Accounts and skeleton

Copernicus, Bhashini and Sarvam registrations on day one — approval is not instant, and it is the only lead time left on this plan. One ERDDAP query returning real numbers, FastAPI and Postgres up in Compose, repo and CLAUDE.md with the decisions on this page. File the SDR loan request with the MAIT communications lab in the same sitting: it costs nothing and blocks nothing.

Gate: a real SST value for a real lat/lon, fetched in code.

D3–D6

### Data plane

Source registry, xarray fetch and subset layer, Zarr cache, PostGIS load of EEZ, IMBL and MPA polygons, PFZ scraper with attribution.

Gate: one function answers "conditions at this point, now" from four sources.

D7–D10

### Graph and risk engine

LangGraph nodes 0 and 2–6, threshold table per boat class, evidence bundle schema, numeric firewall validator with its own unit tests.

Gate: firewall catches an injected fake number in CI.

D11–D13

### Capsule codec

Encoder, decoder, 256-entry reason codebook, 12-language template pack, QR, Bluetooth and SMS transport, airplane-mode decode on a phone. The TypeScript decoder for the PWA runs the same corpus as the Python one in CI.

Gate: a phone in airplane mode scans a QR and speaks a full Tamil advisory.

D14–D17

### Interfaces

Boat surface first (verdict card, evidence card, PFZ compass, countdown), then the shore console and its broadcast composer, then the study routes. Bhashini voice loop, IVR flow, WhatsApp path.

Gate: a spoken Tamil question returns a spoken Tamil answer with a map.

D18–D21

### Evaluation and rehearsal

60-query benchmark, latency profiling, catch-feedback scoring, failure drills (API down, no network), deck, and three timed run-throughs.

Gate: full demo twice in a row with no operator rescue.

Proof

## Evaluation targets

Build the benchmark in week one and quote it on the final slide. Teams that show measured numbers beat teams that show a working demo, because a demo is one sample.

Numeric provenance

100%

Every figure traceable to a dataset cell. Hard gate in CI, not a target.

Intent routing

≥ 92%

On a 60-query set spanning the eight question types in the PS.

p95 latency

≤ 6 s

Online path. Offline capsule decode budget is 400 ms.

Boundary lead time

≥ 20 min

Median warning before projected IMBL crossing in replayed tracks.

Exposure

## Risks worth naming before a judge does

| Risk | Mitigation |
|---|---|
| We cannot transmit on NavIC, so a judge asks whether the offline demo is staged | Say it before they do. The uplink is ISRO's; our claim is segment conformance, which is arithmetic and checkable against the field table on this page. The identical bitstream runs over QR, Bluetooth and SMS, and the capsule inspector shows the actual 145 bits on screen. No rung of that ladder needs hardware we do not have. |
| Free-form questions asked offline | Published offline envelope, and a UI state that says plainly what it cannot answer without a link rather than guessing. |
| PFZ has no machine interface | Scraper plus cache plus visible attribution, and a written note that a formal INCOIS feed is the production path. |
| Bhashini rate limits or downtime during the demo | IndicTrans2 and a local TTS pinned in the image; pre-warmed audio for the scripted queries. |
| Advice is safety-critical | Every response carries "advisory only, follow official INCOIS and IMD warnings", and NO-GO always dominates a favourable PFZ. |
| Vessel positions are personal data | Positions quantised to the 0.05° grid at rest, tracks purged after 7 days, no third-party analytics. Say this unprompted. |
| Oracle A1 free tier under demo load | Pre-computed Zarr for the demo bounding box; the live path is proven once, then served warm. |

Demo

## Six beats, eight minutes

1. Spoken Tamil question from a phone: "நாளை காலை கடலுக்குப் போகலாமா?" Answer returns spoken, with a map and a CAUTION chip.

2. Open the evidence panel. Wave height 2.5 m from a named dataset and timestamp, the threshold that fired, the rule ID. Invite them to check the number.

3. Ask for the nearest PFZ and a safe route to it. Show the cost grid and the no-go mask, then the waypoints and fuel proxy.

4. Airplane mode. Ask again. The 145-bit capsule from before decodes on-device and speaks a full advisory with no network. This is the moment that wins the room.

5. Drift toward the IMBL on a replayed track. Alert fires 34 minutes ahead, in the local language, still offline.

6. Why has the catch fallen here? Marine heatwave over 11 days, chlorophyll anomaly series, method named — then the benchmark slide.

Assumptions: three-week build, team splitting into data plane, agent graph, codec and interfaces; judged on an ISRO panel that values ISRO-native infrastructure. If any of those is wrong, the phase table moves — the wedge does not.

Grounding: ISRO signal-in-space ICD for INCOIS messages via IRNSS (220-bit segments, message IDs 20 and 21, L5 at 1176.45 MHz) · GNSS-SDR IRNSS L5 performance, NAVIGATION 70(2) · INCOIS ERDDAP Oceansat-2 datasets · Copernicus Marine Toolbox · Open-Meteo Marine · NASA PACE OB.DAAC · Marine Regions EEZ · Bhashini ULCA · Sarvam model and speech APIs · Hobday et al. marine heatwave definition.

---

# Part 3 — Implementation Contract

Build instructions for ISRO PS 26176 (ORCA). This file is the working contract: it assumes the
decisions in the plan are settled and does not re-open them. Work top to bottom. Every phase ends
in a gate — do not start the next phase until the gate passes.

**What we are building:** reasoning runs onshore, answers survive offshore. The full advisory
compresses to 145 bits (one NavIC segment is 220), and the phone reconstructs a spoken
regional-language explanation with no network.

---

## Phase 0 — Toolchain (do this first, ~45 min)

### 0.1 Claude Code plugins

Run each inside a Claude Code session. The official marketplace is built in.

```
/plugin install pyright-lsp@claude-plugins-official
/plugin install typescript-lsp@claude-plugins-official
/plugin install context7@claude-plugins-official
/plugin install mcp-server-dev@claude-plugins-official
/plugin install security-guidance@claude-plugins-official
/plugin install code-review@claude-plugins-official
/plugin install github@claude-plugins-official
```

| Plugin | Why it is here |
|---|---|
| `pyright-lsp` | Real type errors across the agent graph and the codec. Catches bit-width mistakes early. |
| `typescript-lsp` | Same for the React/deck.gl frontend. |
| `context7` | Current docs for LangGraph, xarray, deck.gl, copernicusmarine. These libraries move fast and stale API guesses cost hours. |
| `mcp-server-dev` | We write our own MCP wrappers for ERDDAP and Copernicus; none exist. |
| `security-guidance` | We handle live vessel positions and six API keys. |
| `code-review` | Multi-agent review before merges once more than one person is committing. |
| `github` | Issues and PRs from inside the session. |

Language servers need binaries on the machine:

```bash
npm i -g pyright typescript typescript-language-server
```

Add later, only when the phase needs them: `frontend-design` (D14), `duckdb-skills` (data
exploration), `document-skills@anthropic-agent-skills` for the pptx deck (D18).

Do **not** install ECC, awesome-claude-code-toolkit, or any other mega-bundle. They add hundreds of
generic skill descriptions to every session's context and none of them know anything about ocean
data.

### 0.2 MCP servers for development

These help us *write* the system. They are not part of the product.

```
claude mcp add open-meteo -- npx -y open-meteo-mcp
```

Optional, if the geospatial work gets heavy: `gis-mcp` (PyPI, `pip install gis-mcp`) for shapely
and pyproj operations through natural language.

### 0.3 Project subagents

Create these in `.claude/agents/` in the repo root. They exist because the same three mistakes
recur in this domain.

**`.claude/agents/erddap-explorer.md`**

```markdown
---
name: erddap-explorer
description: Queries INCOIS ERDDAP and Copernicus, inspects NetCDF structure, and writes fetch code. Use for any task involving dataset discovery, griddap URLs, or xarray loading.
tools: Bash, Read, Write, Edit, WebFetch
model: sonnet
---

You work with oceanographic data servers.

ERDDAP griddap URL form:
  {base}/erddap/griddap/{datasetID}.{ext}?{var}[({t_start}):{stride}:({t_end})][({lat_min}):({lat_max})][({lon_min}):({lon_max})]
Extensions: .json for small probes, .nc for real subsets, .csv for eyeballing.

Rules:
- Always call the dataset's /info page before writing a query. Never assume variable names,
  dimension order, or time units.
- INCOIS ERDDAP has a TLS chain that fails verification on some hosts. Pin the CA bundle.
  Never pass verify=False.
- Time dimensions are frequently cf-time, not datetime64. Decode with cftime, check calendar.
- Longitudes may be 0-360 or -180-180. Check before subsetting the Indian Ocean.
- Report the actual numbers you got back, with units, not just that the call succeeded.
```

**`.claude/agents/geo-reviewer.md`**

```markdown
---
name: geo-reviewer
description: Reviews geospatial code for CRS errors, coordinate order bugs, and boundary logic mistakes. Use before merging anything touching lat/lon, PostGIS, distances, or the EEZ/IMBL layers.
tools: Read, Grep, Glob, Bash
model: sonnet
---

You review geospatial code for the specific errors that survive testing.

Check every time:
- Coordinate order. shapely is (x=lon, y=lat). Most marine data is (lat, lon). Most bugs live here.
- CRS. Distances in EPSG:4326 degrees are wrong. Project to EPSG:32643/32644 (UTM 43N/44N for
  the Indian coast) or use geodesic distance. Never trust a degree-based buffer.
- Antimeridian and pole handling can be ignored for the Indian EEZ. Say so rather than adding
  dead code.
- Boundary semantics. "Distance to IMBL" is distance to a line, not to a polygon centroid.
  Drift projection must use surface current plus heading, and must state its assumed time step.
- Any rendered boundary must be labelled indicative. We are not publishing legal lines.

Report file:line and the concrete failing case. Do not restate what the code does.
```

**`.claude/agents/capsule-auditor.md`**

```markdown
---
name: capsule-auditor
description: Verifies the 145-bit capsule codec — field widths, offsets, round-trip fidelity, and the bit budget. Use after any change to codec code, the field table, or the reason codebook.
tools: Read, Bash, Grep
model: sonnet
---

You audit the capsule codec against docs/CAPSULE_SPEC.md.

Verify on every change:
- Total width is exactly 145 bits and no field overlaps another. Recompute offsets from widths
  rather than trusting the constants.
- Every quantiser clamps. An out-of-range wave height must saturate, never wrap. Wrapping turns
  a 9 m sea into a calm one.
- Round-trip: encode(decode(x)) == x for the full corpus in eval/capsule_corpus.jsonl.
- Decoder is pure. No network, no filesystem, no clock. It must run offline forever.
- The reason codebook has exactly 256 entries and every entry renders in all 12 languages.

Fail loudly on drift between the spec table and the code.
```

### 0.4 CLAUDE.md

Write `CLAUDE.md` at the repo root containing: the stack table from the plan, the data source
table with its traps, the numeric-firewall rule, and the line "PFZ has no API — it is scraped and
attributed." Without this every session re-derives the architecture and occasionally re-litigates
it.

### 0.5 Accounts (start now, approval is not instant)

- Copernicus Marine — account, then `pip install copernicusmarine` and `copernicusmarine login`
- Bhashini — ULCA registration, note the two-step config-then-compute handshake
- Sarvam — API key from the dashboard
- NASA Earthdata — only if PACE enrichment is in scope
- Open-Meteo, INCOIS ERDDAP — no key needed

Nobody buys hardware. Transport for the offline demo is QR, Bluetooth and SMS. One person files a
request with the MAIT communications lab for an RTL-SDR or USRP, because free hardware is worth
asking for and paid hardware is not.

**Gate 0:** `/plugin list` shows the seven plugins, the three subagents load, and `CLAUDE.md`
exists. One ERDDAP query returns a real SST number for a real lat/lon.

---

## Phase 1 — Repo and skeleton (D1–D2)

```
dhruva/
├── CLAUDE.md
├── docker-compose.yml
├── .env.example
├── .claude/agents/            # the three subagents above
├── backend/
│   ├── pyproject.toml
│   ├── dhruva/
│   │   ├── api/               # FastAPI routers
│   │   ├── graph/             # LangGraph nodes, state, edges
│   │   ├── sources/           # erddap.py, copernicus.py, openmeteo.py, pfz_scraper.py
│   │   ├── analytics/         # fronts.py, anomaly.py, heatwave.py
│   │   ├── geo/               # boundaries.py, drift.py, routing.py
│   │   ├── risk/              # thresholds.py, rules.py
│   │   ├── evidence/          # schema.py, firewall.py
│   │   ├── codec/             # encode.py, decode.py, codebook.py
│   │   └── lang/              # bhashini.py, sarvam.py
│   └── tests/
├── frontend/                  # Vite + React + TS
│   └── src/{boat,shore,study,shared}/
├── data/
│   ├── registry.yaml          # dataset catalogue
│   ├── codebook/              # 256 reason templates × 12 languages
│   └── layers/                # EEZ, IMBL, MPA shapefiles
├── eval/
│   ├── queries.jsonl          # 60-query benchmark
│   └── capsule_corpus.jsonl
└── docs/
    ├── CAPSULE_SPEC.md
    └── THRESHOLDS.md
```

Python toolchain: `uv` if available, else pip + venv. Lint with `ruff`, format with `ruff format`,
test with `pytest`. Type-check with `pyright` in CI.

Services in `docker-compose.yml`: `api`, `postgres` (PostGIS + pgvector + TimescaleDB),
`redis`, `langfuse`, `caddy`.

**Gate 1:** `docker compose up` brings the stack online, `/health` returns 200, `pytest` runs
green on an empty suite.

---

## Phase 2 — Data plane (D3–D6)

1. **Source registry** (`data/registry.yaml`). Each entry: variable, source, dataset ID, spatial
   and temporal extent, resolution, units, latency, auth. The discovery node reads this; adding a
   dataset must never require code.
2. **Fetch layer** (`sources/`). One function per source returning an `xarray.Dataset` subset.
   All of them normalise to: lat ascending, lon in -180..180, time in UTC, SI units.
3. **Zarr cache.** Key on (dataset, bbox, time window, variables). The demo bounding box is
   pre-warmed. Cold queries must still work, just slower.
4. **PostGIS layers.** Load EEZ, IMBL and MPA polygons from Marine Regions. Index with GiST.
   Store an `indicative` flag on every boundary row and carry it to the UI.
5. **PFZ scraper.** Pull the INCOIS bulletin, parse lat/lon/depth/bearing, store with
   `source_url` and `fetched_at`. Cache aggressively; their site is not fast and we are guests.

**Gate 2:** one function `conditions_at(lat, lon, when)` returns wave, wind, current, SST and
chlorophyll from four sources with units and timestamps, in under 3 s warm.

---

## Phase 3 — Graph and risk engine (D7–D10)

### 3.1 Nodes

Implement as LangGraph nodes over a typed state object: `planner(0)`, `discovery(2)`,
`ocean(3)`, `weather(4)`, `geo(5)`, `risk(6)`, `route(7)`, `evidence(8)`, `codec(9)`.
Language (1) wraps the graph — everything inside runs in English.

Nodes 2–5 run in parallel. The planner emits a tool plan; it does not call tools itself.

### 3.2 Risk thresholds

`docs/THRESHOLDS.md` holds the table. Starting values, **clearly marked provisional**:

| Boat class | Caution H_s | No-go H_s | Caution wind | No-go wind |
|---|---|---|---|---|
| FRP / country craft < 12 m | 2.0 m | 3.0 m | 20 kt | 28 kt |
| Mechanised 12–20 m | 2.5 m | 3.5 m | 25 kt | 33 kt |
| Deep-sea > 20 m | 3.5 m | 4.5 m | 30 kt | 40 kt |

Absolute overrides regardless of class: active cyclone warning within 300 km, lightning within
50 km, or any tsunami alert → NO-GO.

> These numbers are engineering placeholders. Before any public claim, replace them with the
> published INCOIS Ocean State Forecast criteria and cite the source in the file. Never present
> invented safety thresholds as official.

### 3.3 Numeric firewall

The rule: the model may not introduce a number.

```
1. Tools produce an EvidenceBundle: list of {key, value, unit, dataset_id, cell, valid_time,
   threshold?, rule_id?}.
2. The LLM receives the bundle and writes narration.
3. The validator extracts every numeric token from the narration — ASCII and Indic digits,
   plus spelled-out numerals in the target language.
4. Each extracted value must match a bundle value, within rounding tolerance, or appear in the
   explicitly allowed derived set (unit conversions declared per field, e.g. m→ft, kt→km/h).
5. On failure: one retry with a stricter prompt. On second failure: render the pure template
   and log the incident. Never ship the unvalidated string.
```

Test it with adversarial cases in `tests/test_firewall.py`: an injected fabricated wave height,
a hallucinated distance, a converted unit that was not declared, a Tamil numeral.

**Gate 3:** CI fails when a fabricated number is injected into narration. Eight PS query types
route to the right node set.

---

## Phase 4 — Capsule codec (D11–D13)

Full field table lives in `docs/CAPSULE_SPEC.md`. Bit layout, MSB-first, total **145 bits**:

| Offset | Width | Field | Encoding |
|---:|---:|---|---|
| 0 | 4 | msg_type | 0=advisory, 1=alert, 2=all-clear, 3=test |
| 4 | 3 | schema_ver | integer |
| 7 | 10 | issue_slot | 15-min slots, 7-day wrap (0–671) |
| 17 | 4 | valid_hours | 0–15 |
| 21 | 20 | zone_id | `lat_idx * 560 + lon_idx`, bbox 6–24 °N / 66–94 °E, step 0.05° |
| 41 | 8 | lat_offset | position in cell, 0.05/256 ≈ 22 m |
| 49 | 8 | lon_offset | same |
| 57 | 2 | risk_class | 0=safe, 1=caution, 2=no-go, 3=unknown |
| 59 | 8 | hazard_flags | bitmap: wave, wind, squall, lightning, cyclone, current, fog, tsunami |
| 67 | 5 | wave_hs | `round(H_s / 0.25)`, 0–7.75 m, saturating |
| 72 | 6 | wind_kt | 0–63 kt, saturating |
| 78 | 4 | wind_dir | 16-point compass index |
| 82 | 5 | curr_kt | `round(kt / 0.1)`, 0–3.1 kt |
| 87 | 4 | curr_dir | 16-point |
| 91 | 5 | sst | `round((°C − 18) / 0.5)`, 18–33.5 °C |
| 96 | 2 | chl_class | 0=low, 1=moderate, 2=high, 3=very high |
| 98 | 4 | pfz_bearing | 16-point |
| 102 | 6 | pfz_dist_nm | 0–63 nm |
| 108 | 2 | pfz_conf | 0–3 |
| 110 | 5 | bnd_dist_nm | 0–31 nm |
| 115 | 2 | bnd_type | 0=none, 1=IMBL, 2=MPA, 3=closed |
| 117 | 8 | bnd_eta_min | 0–255 min, drift-projected |
| 125 | 8 | reason_code | codebook index |
| 133 | 12 | evidence_hash | truncated SHA-256 of the bundle, for audit |

145 used, **75 free** inside a 220-bit segment. Reserved use for the free bits: a 4-waypoint
return route at reduced precision when `risk_class == 2`.

Implementation notes:

- Use `bitstruct` or hand-rolled shifts. Write the field table once as data and generate both
  encoder and decoder from it, so they cannot drift apart.
- Every quantiser **clamps**. Wrapping a 9 m sea into a calm reading is the worst bug this
  project can ship.
- The decoder must be pure — no network, no filesystem, no clock — and must be ported to
  TypeScript for the PWA. Both implementations run the same corpus in CI.
- Reason codebook: 256 entries, each a template with slots filled from capsule fields, translated
  into 12 languages. The server chooses the index; the phone renders the sentence.
- Transports: QR (19 bytes, base32 for scanner reliability), Bluetooth, SMS. The wire format is
  identical across all three.

**Gate 4:** a phone in airplane mode scans a QR and speaks a full Tamil advisory. Round-trip
tests pass in both Python and TypeScript.

---

## Phase 5 — Interfaces (D14–D17)

Build in this order; the boat surface is the one that must be finished.

**Boat (PWA).** Verdict card → readout → PFZ row → boundary countdown → buttons. Constraints are
binding, not aspirational: 7:1 contrast, 56 px touch targets, colour never carrying the verdict
alone, data age visible on every screen, NO-GO rendering above any favourable fishing zone.
Offline via service worker + Dexie: codebook, last capsules, cached fields, map tiles for the
coastal window only.

**Shore console.** Fleet list with status, breach watch, MapLibre + deck.gl layers (SST,
chlorophyll, H_s, PFZ zones, boundaries), broadcast composer showing payload cost before send.

**Study routes.** Anomaly explorer, time series, marine heatwave view, Langfuse trace inspector.

**Voice.** Bhashini ASR → graph → Bhashini TTS, with Sarvam Saarika/Bulbul as the fallback and
the better demo voice. IVR through Asterisk for the feature-phone path.

**Gate 5:** spoken Tamil question returns a spoken Tamil answer with a map and a tappable
evidence card, end to end.

---

## Phase 6 — Evaluation (D18–D21)

`eval/queries.jsonl` — 60 queries covering all eight PS question types, each with expected
intent, expected tool set, and a ground-truth answer sourced from INCOIS or IMD bulletins for
that date. Record the source for every ground truth; unsourced expectations are worthless.

| Metric | Target | Method |
|---|---|---|
| Numeric provenance | 100% | Firewall pass rate over the whole eval set. Hard gate. |
| Intent routing | ≥ 92% | Predicted vs expected node set |
| p95 latency | ≤ 6 s online, ≤ 400 ms capsule decode | Langfuse traces |
| Boundary lead time | ≥ 20 min median | Replayed vessel tracks against known crossings |
| Language round-trip | chrF ≥ 55 | Back-translation on the query set |

Failure drills before the demo: Bhashini down, Copernicus timing out, no network at all, and a
deliberately poisoned scraped bulletin. Each must degrade visibly rather than silently.

---

## Conventions

- Commits: `area: imperative summary` (`codec: clamp wave quantiser at 7.75 m`).
- One PR per phase gate. `code-review` plugin runs before merge.
- Every number rendered anywhere carries its evidence. No exceptions, including in the console.
- Vessel positions quantise to the 0.05° grid at rest; tracks purge after 7 days; no third-party
  analytics anywhere in the frontend.
- Every advisory response carries: advisory only, follow official INCOIS and IMD warnings.

## Working with Claude Code on this repo

One phase per session. Start each with "read CLAUDE.md and IMPLEMENTATION.md, we are on Phase N."
Use `erddap-explorer` for anything touching datasets, `geo-reviewer` before merging geospatial
code, and `capsule-auditor` after every codec change. Let the gates decide when to move on — the
temptation near a deadline is to skip Phase 3's firewall tests, and that is the one thing that
makes the whole pitch collapse under a judge's question.
