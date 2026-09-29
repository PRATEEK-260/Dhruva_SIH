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

# Must match EN_LABELS and EN_REASONS in frontend/src/shared/verdict.ts. The
# line is the action, first: what to do, before why.
EN_LABELS = {
    "safe": ("Safe", "You can go to sea."),
    "caution": ("Caution", "Go only with care."),
    "unsafe": ("Unsafe", "Do not go to sea."),
    "blocked": ("Blocked", "Do not go to sea. An official warning is active."),
    "unavailable": ("No data", "Check the official warning before you go."),
}

# One short reason, with no numbers; the figures are spoken, and shown only
# under "Show evidence".
EN_REASONS = {
    "safe": "Waves and wind are within your boat's limits.",
    "caution_wave": "The waves are near your boat's limit.",
    "caution_wind": "The wind is near your boat's limit.",
    "caution_alert": "A warning is out that could not be checked.",
    "unsafe_wave": "The waves are too high for your boat.",
    "unsafe_wind": "The wind is too strong for your boat.",
    "blocked_cyclone": "A cyclone warning is active near you.",
    "blocked_lightning": "Lightning is reported near you.",
    "blocked_tsunami": "A tsunami alert is in force.",
    "unavailable": "The sea could not be checked.",
}

# The pilot states (Tamil Nadu, Kerala, Odisha) plus Hindi.
LANGUAGES = ("ta", "ml", "or", "hi")

ROOT = Path(__file__).resolve().parent.parent
LABELS_OUT = ROOT / "frontend/src/shared/verdict-labels.json"
REASONS_OUT = ROOT / "frontend/src/shared/verdict-reasons.json"
VOICE_OUT = ROOT / "frontend/public/voice"


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}


async def main() -> None:
    """Translates what is missing or changed and keeps the rest, so a word a
    native speaker corrected by hand in the JSON is never overwritten. A clip is
    remade whenever its line changes."""
    key = os.environ["BHASHINI_INFERENCE_API_KEY"]
    labels = _load(LABELS_OUT)
    reasons = _load(REASONS_OUT)
    source = labels.pop("_source", {})
    async with httpx.AsyncClient() as client:
        for lang in LANGUAGES:
            labels.setdefault(lang, {})
            reasons.setdefault(lang, {})
            (VOICE_OUT / lang).mkdir(parents=True, exist_ok=True)
            for state, (word, line) in EN_LABELS.items():
                entry = labels[lang].setdefault(state, {})
                if "word" not in entry:
                    entry["word"] = (
                        await bhashini.translate(client, key, word, "en", lang)
                    ).rstrip(".")
                changed = source.get(state) != line or "line" not in entry
                if changed:
                    entry["line"] = await bhashini.translate(client, key, line, "en", lang)
                clip = VOICE_OUT / lang / f"{state}.wav"
                status = "clip kept"
                if changed or not clip.exists():
                    try:
                        audio = await bhashini.tts(
                            client, key, entry["line"], lang, sample_rate=16000
                        )
                        clip.write_bytes(audio)
                        status = "clip made"
                    except httpx.HTTPError as e:
                        # The phone falls back to its own voice for a missing clip.
                        status = f"NO CLIP ({type(e).__name__})"
                print(f"{lang} {state:<12} {status:<22} {entry['word']} | {entry['line']}")
            for rkey, text in EN_REASONS.items():
                if reasons[lang].get(f"_en_{rkey}") != text:
                    reasons[lang][rkey] = await bhashini.translate(client, key, text, "en", lang)
                    reasons[lang][f"_en_{rkey}"] = text
                print(f"{lang} {rkey:<18} {reasons[lang][rkey]}")
    labels["_source"] = {state: line for state, (_, line) in EN_LABELS.items()}
    LABELS_OUT.write_text(json.dumps(labels, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    REASONS_OUT.write_text(
        json.dumps(reasons, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(
        f"wrote {LABELS_OUT.name}, {REASONS_OUT.name} and {VOICE_OUT.relative_to(ROOT)}/"
    )


if __name__ == "__main__":
    asyncio.run(main())
