#!/usr/bin/env python
"""Translate the five verdict labels and pre-generate their voice clips.

The phone speaks these at sea with no network, so they are made here, onshore,
with Bhashini, and shipped in the app:

    frontend/src/shared/verdict-labels.json     word + line per state per language
    frontend/public/voice/<lang>/<state>.wav    the line, spoken

Machine translation. A native speaker should check every string before any
public claim.

    set -a; . ./.env; set +a
    PYTHONPATH=backend .venv/bin/python scripts/verdict_labels.py
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import httpx

from dhruva.lang import bhashini

# Must match EN_LABELS in frontend/src/shared/verdict.ts.
EN_LABELS = {
    "safe": ("Safe", "Conditions are within the limits for your boat."),
    "caution": ("Caution", "Conditions are near the limit for your boat. Take care."),
    "unsafe": ("Unsafe", "Do not go to sea. The sea is too rough for your boat."),
    "blocked": ("Blocked", "Do not go to sea. An official warning is active."),
    "unavailable": ("No data", "The sea could not be checked. Follow the official warning."),
}

# The pilot states (Tamil Nadu, Kerala, Odisha) plus Hindi.
LANGUAGES = ("ta", "ml", "or", "hi")

ROOT = Path(__file__).resolve().parent.parent
LABELS_OUT = ROOT / "frontend/src/shared/verdict-labels.json"
VOICE_OUT = ROOT / "frontend/public/voice"


async def main() -> None:
    key = os.environ["BHASHINI_INFERENCE_API_KEY"]
    out: dict[str, dict[str, dict[str, str]]] = {}
    async with httpx.AsyncClient() as client:
        for lang in LANGUAGES:
            out[lang] = {}
            (VOICE_OUT / lang).mkdir(parents=True, exist_ok=True)
            for state, (word, line) in EN_LABELS.items():
                t_word = await bhashini.translate(client, key, word, "en", lang)
                t_line = await bhashini.translate(client, key, line, "en", lang)
                out[lang][state] = {"word": t_word.rstrip("."), "line": t_line}
                clip = VOICE_OUT / lang / f"{state}.wav"
                status = "clip kept"
                if not clip.exists():
                    try:
                        audio = await bhashini.tts(client, key, t_line, lang, sample_rate=16000)
                        clip.write_bytes(audio)
                        status = "clip made"
                    except httpx.HTTPError as e:
                        # The phone falls back to its own voice for a missing clip.
                        status = f"NO CLIP ({type(e).__name__})"
                print(f"{lang} {state:<12} {status:<22} {t_word} | {t_line}")
    LABELS_OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {LABELS_OUT.relative_to(ROOT)} and {VOICE_OUT.relative_to(ROOT)}/")


if __name__ == "__main__":
    asyncio.run(main())
