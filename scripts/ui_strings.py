#!/usr/bin/env python
"""Translate the phone's screen text (frontend/src/shared/ui-strings.json).

The fisherman-facing words of the boat phone in the pilot languages, by
Bhashini. Like scripts/verdict_labels.py it translates only what is missing or
whose English changed, so a word a native speaker corrected by hand is kept.
Strings carry no numbers: a figure on screen always comes from the evidence.

    set -a; . ./.env; set +a
    PYTHONPATH=backend .venv/bin/python scripts/ui_strings.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

from dhruva.lang import bhashini

EN: dict[str, str] = {
    # header and home
    "tagline": "Sea advice for your boat",
    "online": "Online",
    "no_signal": "No signal",
    "ask_before": "Ask before you go",
    "home_body": "Speak your question in your language. DHRUVA checks the sea for your boat and tells you why.",
    "home_offline": "Out of mobile range, answers still reach you through the boat's satellite terminal.",
    "last_answer": "Your last answer",
    "ask": "Ask",
    "receive": "Receive",
    # ask sheet
    "ask_title": "Ask about the sea",
    "ask_satellite": "Ask by satellite",
    "tap_speak": "Tap and speak your question",
    "listening": "Listening. Tap to send",
    "understanding": "Understanding your question",
    "checking": "Checking the sea for your boat",
    "leaving": "Leaving",
    "now": "Now",
    "tomorrow5": "Tomorrow 5 AM",
    "tomorrow7": "Tomorrow 7 AM",
    "type_question": "Or type a question",
    "heard": "Heard",
    "no_mic": "The microphone is not available. Allow it, or tap a question below.",
    # answer
    "listen_again": "Listen again",
    "understood": "I understand",
    "answered_online": "Answered online at",
    "arrived_satellite": "Arrived by satellite message at",
    "replayed": "Replayed from a recorded live run",
    "nearest_harbour": "Nearest harbour",
    "head_back": "Head back to",
    "straight_line": "Straight-line distance, not a route.",
    "worked_offline": "Worked out on this phone from the message's position and the harbour list, with no network.",
    "fishing_hidden": "Fishing-zone advice is hidden while this warning stands. Safety comes first.",
    "nearest_pfz": "Nearest potential fishing zone",
    "no_pfz": "No fresh INCOIS potential-fishing-zone advisory lies near you.",
    "other_time": "What if you leave at another time?",
    "same_as_now": "same as now",
    "show_evidence": "Show evidence",
    "hide_evidence": "Hide evidence",
    "voice_says": "What the voice says",
    "numbers_behind": "The numbers behind this",
    "how_worked": "How DHRUVA worked this out",
    "advisory_only": "Advisory only. Follow official INCOIS and IMD warnings.",
    "official_warning": "Official warning: read the IMD bulletin",
    "no_imd_as_of": "No active IMD cyclone bulletin. Last checked",
    "imd_stale": "IMD's bulletin list has not been checked recently.",
    "imd_unchecked": "IMD cyclone bulletins have not been checked yet.",
    "incois_advisory": "INCOIS advisory of",
    "decline_title": "Why the catch may have changed",
    "normal_here": "Normal here",
    "what_changed": "What changed",
    "possible_reason": "Possible reason",
    "what_to_do": "What to do",
    "title_avoid": "Zones to avoid",
    "title_thunder": "Cyclone and thunderstorm alerts",
    "title_tide": "Tides",
    "title_productive": "High chlorophyll, favourable temperature",
    "title_route": "Straight line to the fishing zone",
    # voice notes
    "voice_bhashini": "Spoken by Bhashini",
    "voice_saved": "Bhashini voice, saved on this phone",
    "voice_shipped": "Bhashini voice, shipped with the app",
    "voice_phone": "Spoken by the phone's own voice",
    "voice_none": "No voice for this language on this phone",
    # evidence row names
    "ev_wave_height": "Wave height",
    "ev_wind_speed": "Wind",
    "ev_wind_direction": "Wind from",
    "ev_sst": "Sea temperature",
    "ev_chlorophyll": "Chlorophyll",
    "ev_current_speed": "Current",
    "ev_cyclone_distance": "Cyclone distance",
    "ev_pfz_distance": "Potential fishing zone",
    "ev_high_water": "High water",
    "ev_low_water": "Low water",
    "ev_thunderstorm_from": "Thunderstorm forecast from",
    "ev_route_max_wave": "Highest wave along the line",
}

LANGUAGES = ("ta", "ml", "or", "hi")
OUT = Path(__file__).resolve().parent.parent / "frontend/src/shared/ui-strings.json"


async def main() -> None:
    key = os.environ["BHASHINI_INFERENCE_API_KEY"]
    table = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    table["en"] = EN
    async with httpx.AsyncClient() as client:
        for lang in LANGUAGES:
            out = table.setdefault(lang, {})
            src = out.setdefault("_en", {})
            for k, text in EN.items():
                if src.get(k) == text and k in out:
                    continue
                out[k] = await bhashini.translate(client, key, text, "en", lang)
                src[k] = text
                print(f"{lang} {k:<20} {out[k]}")
    OUT.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    asyncio.run(main())
