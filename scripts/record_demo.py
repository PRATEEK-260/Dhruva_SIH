#!/usr/bin/env python
"""Record real /advisory runs for every request the demo makes, so the video
survives a source going down mid-take.

Each request goes through the real app with DHRUVA_DEMO=off, so every number,
source and capsule in the recording came from a live run at recording time.
Recordings are written to data/demo/recordings.json with the time they were
made; a replayed answer is labelled with it on screen (dhruva/demo/replay.py).

It also pre-speaks each answer with Bhashini into the voice cache
(backend/.voice-cache), so the spoken answer survives a Bhashini outage too.

The request set is read from the same files the screens use:
frontend/src/shared/questions.json and demo.json.

    set -a; . ./.env; set +a
    export DHRUVA_DSN="postgresql://dhruva:${POSTGRES_PASSWORD}@localhost:55432/dhruva"
    PYTHONPATH=backend .venv/bin/python scripts/record_demo.py
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import math
import os
import sys
import time
from pathlib import Path
from typing import Any

os.environ["DHRUVA_DEMO"] = "off"  # record live runs only, never a replay

import httpx
from fastapi.testclient import TestClient

from dhruva.api.voice import cache_path
from dhruva.app import app
from dhruva.codec.codebook import render
from dhruva.codec.codec import decode, from_base32
from dhruva.demo import replay
from dhruva.demo.boats import DEMO_BOATS
from dhruva.lang import bhashini

ROOT = Path(__file__).resolve().parent.parent
SHARED = ROOT / "frontend/src/shared"
OUT = ROOT / "data/demo/recordings.json"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
PACE_S = float(os.environ.get("DHRUVA_LIVE_PACE_S", "4.5"))  # Gemini free tier: 15/min

QUESTIONS = json.loads((SHARED / "questions.json").read_text(encoding="utf-8"))
DEMO = json.loads((SHARED / "demo.json").read_text(encoding="utf-8"))
LABELS = json.loads((SHARED / "verdict-labels.json").read_text(encoding="utf-8"))

# The shore console's point-check query (ShoreApp.tsx GO_NO_GO_QUERY).
SHORE_QUERY = "Is it safe to go out at this position?"
ALERT_QUERY = "Is there a cyclone warning?"
TERMINAL_ALERT_KM = 180  # EmulatorApp.tsx TEST_CYCLONE_KM


def departure(d: str, now: dt.datetime) -> str | None:
    """Mirror of questions.ts departureTime()."""
    if d == "now":
        return None
    hour = 5 if d == "tomorrow5" else 7
    ist = now.astimezone(IST)
    tomorrow = (ist + dt.timedelta(days=1)).date()
    return dt.datetime.combine(tomorrow, dt.time(hour), tzinfo=IST).astimezone(dt.UTC).isoformat()


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Mirror of harbour.ts distanceKm(), so Warn boats' rounded km match."""
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin(math.radians(lat2 - lat1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(a))


def text(q: dict[str, Any], lang: str) -> str:
    return q["text"].get(lang, q["text"]["en"])


def requests(now: dt.datetime) -> list[dict[str, Any]]:
    boat, storm, cyc = DEMO["boat"], DEMO["storm"], DEMO["cyclone"]
    out: list[dict[str, Any]] = []

    def add(**r: Any) -> None:
        r.setdefault("lat", boat["lat"])
        r.setdefault("lon", boat["lon"])
        r.setdefault("boat_class", "frp_under_12m")
        out.append(r)

    # Phone and terminal questions, in every demo language; both go/no-go
    # questions at every departure, for the "what if you leave at 7" buttons.
    for lang in ("ta", "en", "hi", "ml", "or"):
        for q in QUESTIONS:
            # The go/no-go question at every Leaving option; the rest at "now".
            departures = ["now", "tomorrow5", "tomorrow7"] if q["code"] == 1 else ["now"]
            for d in departures:
                add(query=text(q, lang), language=lang, when=departure(d, now))
        # Terminal: simulated cyclone alert.
        add(query=ALERT_QUERY, language=lang, test_cyclone_km=TERMINAL_ALERT_KM)
        # Terminal: replay of a real storm, for the boat at the storm point.
        q2 = next(q for q in QUESTIONS if q["code"] == 1)
        add(
            query=text(q2, lang),
            language=lang,
            lat=storm["lat"],
            lon=storm["lon"],
            when=storm["when"],
        )

    # Shore console point checks: the demo boat by boat class, and the storm.
    for cls in ("frp_under_12m", "mechanised_12_20m", "deep_sea_over_20m"):
        add(query=SHORE_QUERY, language="en", boat_class=cls)
    add(
        query=SHORE_QUERY,
        language="en",
        lat=storm["lat"],
        lon=storm["lon"],
        when=storm["when"],
    )

    # Warn boats with the demo cyclone: every demo boat and the demo point.
    for b in [*DEMO_BOATS, boat]:
        km = distance_km(cyc["lat"], cyc["lon"], b["lat"], b["lon"])
        add(
            query=ALERT_QUERY,
            language="ta",
            lat=b["lat"],
            lon=b["lon"],
            test_cyclone_km=round(km),
        )
    return out


def state_of(capsule: Any) -> str:
    """Mirror of verdict.ts verdictState()."""
    if capsule.risk_class == "no_go":
        return "blocked" if {"cyclone", "lightning", "tsunami"} & set(capsule.hazards) else "unsafe"
    return {"safe": "safe", "caution": "caution"}.get(capsule.risk_class, "unavailable")


async def prewarm(entries: dict[str, dict[str, Any]], languages: set[str]) -> None:
    """Speak what the phone will say (BoatApp say(): '<word>. <sentence>')."""
    key = os.environ.get("BHASHINI_INFERENCE_API_KEY")
    if not key:
        print("no BHASHINI_INFERENCE_API_KEY: voice cache not warmed")
        return
    texts: set[tuple[str, str]] = set()
    for entry in entries.values():
        capsule = decode(from_base32(entry["capsule_base32"]))
        for lang in languages:
            if lang in LABELS:
                texts.add(
                    (
                        lang,
                        f"{LABELS[lang][state_of(capsule)]['word']}. {render(capsule, lang)}",
                    )
                )
    made = 0
    async with httpx.AsyncClient() as client:
        for lang, t in sorted(texts):
            path = cache_path(t, lang, "female")
            if path.exists():
                continue
            try:
                audio = await bhashini.tts(client, key, t, lang)
            except httpx.HTTPError as e:
                print(f"  voice {lang}: {type(e).__name__}, skipped")
                continue
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)
            made += 1
    print(f"voice cache: {made} new clips, {len(texts)} sentences in all")


def _planner_line(data: dict[str, Any]) -> str:
    return next((t["line"] for t in data.get("trace", []) if t["node"] == "planner"), "")


def _save(entries: dict[str, dict[str, Any]], now: dt.datetime) -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    body = {"recorded_at": now.isoformat(), "entries": entries}
    OUT.write_text(json.dumps(body, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")


def main() -> None:
    """Saves after every request, so an interrupted run keeps what it recorded.
    Re-running upgrades entries: a keyword-routed recording is replaced by a
    Gemini-routed one, never the other way round."""
    now = dt.datetime.now(dt.UTC)
    reqs = requests(now)
    entries: dict[str, dict[str, Any]] = dict(replay.recordings(OUT).get("entries", {}))
    attempts = int(os.environ.get("DHRUVA_RECORD_ATTEMPTS", "1"))
    client = TestClient(app)
    print(
        f"recording {len(reqs)} requests, {PACE_S}s apart, {attempts} attempt(s) each", flush=True
    )

    for i, r in enumerate(reqs, 1):
        when = dt.datetime.fromisoformat(r["when"]) if r.get("when") else None
        k = replay.key(
            r["query"],
            r["language"],
            r["lat"],
            r["lon"],
            r["boat_class"],
            when,
            r.get("test_cyclone_km"),
        )
        old = entries.get(k)
        if old and _planner_line(old).startswith("Gemini") and "--refresh" not in sys.argv:
            print(f"  [{i}/{len(reqs)}] kept   (already Gemini-routed) {k[:80]}", flush=True)
            continue
        body = {**{k2: v for k2, v in r.items() if v is not None}, "log": False}
        best = None
        for attempt in range(attempts):
            time.sleep(PACE_S)
            res = client.post("/advisory", json=body)
            if res.status_code != 200:
                print(f"  [{i}] HTTP {res.status_code}", flush=True)
                continue
            best = res.json()
            if _planner_line(best).startswith("Gemini") or attempt == attempts - 1:
                break
        if best is None:
            print(f"  [{i}/{len(reqs)}] FAILED {k[:80]}", flush=True)
            continue
        gemini = _planner_line(best).startswith("Gemini")
        if old and _planner_line(old).startswith("Gemini") and not gemini:
            print(f"  [{i}/{len(reqs)}] kept   (new run was keyword) {k[:80]}", flush=True)
            continue
        best = {k2: v for k2, v in best.items() if k2 not in ("recorded_at", "replay_reason")}
        best["recorded_at"] = dt.datetime.now(dt.UTC).isoformat()
        entries[k] = best
        _save(entries, now)
        print(
            f"  [{i}/{len(reqs)}] {best['risk_class']:<8} "
            f"{'gemini ' if gemini else 'keyword'} {k[:80]}",
            flush=True,
        )

    print(f"wrote {len(entries)} recordings to {OUT.relative_to(ROOT)}", flush=True)
    asyncio.run(
        prewarm(entries, {"ta", "ml", "or", "hi"} if "--all-voices" in sys.argv else {"ta"})
    )


if __name__ == "__main__":
    main()
