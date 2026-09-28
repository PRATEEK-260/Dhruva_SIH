# Demo assets — captions

All generated 28 Sep 2026 from live data. Use these captions (or shorter versions that
keep the same facts). Do not caption any of this as INCOIS data.

## sst_chlorophyll_south_india.png
Slide 3 or 4, beside "Data: open & official".

> Sea surface temperature and chlorophyll-a off Kerala and Tamil Nadu, 28 Sep 2026,
> pulled by the DHRUVA pipeline from Copernicus Marine
> (cmems_mod_glo_phy_anfc_0.083deg_PT1H-m, cmems_mod_glo_bgc-pft_anfc_0.25deg_P1D-m).
> Model analysis/forecast. Boundaries indicative, not legal.

## trace_en.png / trace_ta.png
Slide 3, beside the flowchart. Same pipeline, English and Tamil question.

> One question through DHRUVA's agents, live: Gemini routes the intent, unneeded agents
> are skipped, PostGIS places the boat 51.8 nm from the Sri Lanka–India boundary, weather
> is fetched with its source cell and time, and the rule engine — not the model — gives
> the verdict. Thresholds are provisional placeholders.

Keep in mind when presenting:
- The Tamil trace shows the planner understanding Tamil; the answer text is still the
  English template. Do not claim a spoken Tamil answer yet.
- Wind and waves are Open-Meteo forecasts; the wind cell is 15 km from the query point.
- The planner routes; it does not yet split one question into several sub-tasks.

## trace_en.txt / trace_ta.txt
The raw output behind the two images. To reproduce live, from the repo root:

    set -a; . ./.env; set +a
    export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@$(docker inspect $(docker compose ps -q postgres) --format '{{range .NetworkSettings.Networks}}{{.IPAddress}}{{end}}'):5432/dhruva"
    PYTHONPATH=backend .venv/bin/python scripts/trace_query.py "இப்போது கடலுக்குப் போகலாமா?"

## trace_cyclone.png / trace_cyclone.txt
Slide 3 or 4, next to "LLM gives a wrong safety answer".

> The same calm sea, with a simulated cyclone warning 180 km away (clearly labelled test
> input — no live IMD feed is wired yet). Absolute rule CYCLONE-A1 turns the verdict to
> NO-GO regardless of wave height or boat class. The verdict comes from the rule table;
> the model never decides it, so there is no model output to override.

Do not caption it "LLM output overridden": in DHRUVA the LLM never produces the verdict.

## voice_roundtrip.png / .txt, voice_question_ta.wav, voice_answer_ta.wav
Slide 2 next to the "Ask" example, or slide 3's voice card. Label it **Sarvam**, not Bhashini.

> Spoken Tamil question → Sarvam Saaras transcribes it and detects Tamil → DHRUVA's
> agents answer → the Tamil sentence is rendered offline from the 145-bit capsule by the
> shipped codebook (no machine translation) → Sarvam Bulbul speaks it. Voice runs on Sarvam
> today; Bhashini integration is pending.

Keep in mind:
- The question audio is Sarvam TTS standing in for a fisherman's recording. Run with
  `--audio your.wav` to use a real one.
- The spoken answer says 0.25 m where the live reading was 0.26 m: capsule values are
  quantised to a 0.25 m grid. The trace says so.

## shore_console.png
Slide 4 or 5, "what a fisheries officer sees". Label it prototype.

> Shore console prototype: live Copernicus SST layer (valid 29 Sep 00:00Z, forecast),
> Marine Regions boundaries (indicative), the advisory request log, and a live advisory
> for 11.05N 79.95E with its evidence table and the 19-byte capsule a boat would receive,
> rendered in Tamil.

Keep in mind:
- The PFZ layer is switched off because its data is the synthetic test fixture; the
  header chip "PFZ · 1" still counts that row. Crop it or say so.
- The advisory log entries are real graph runs from 65 hours earlier, one a replay of
  1 Aug 2026 conditions.
- The API container runs an older build: its evidence table labels Open-Meteo forecasts
  as "observation" (off-screen in this shot). The current code says "forecast".

## Not here yet
- Bhashini voice round-trip — waiting on the key; Sarvam stands in above.
- PFZ on the map — needs a real INCOIS bulletin instead of the synthetic fixture.
