#!/usr/bin/env python
"""Spoken Tamil question in, spoken Tamil answer out, through the real graph.

Sarvam stands in for Bhashini until the Bhashini key arrives (CLAUDE.md lists
Sarvam Saarika/Bulbul as the fallback and demo voice):

    1. question audio   Sarvam Bulbul TTS speaks the question text (a stand-in for a
                        fisherman's recording; pass --audio to use a real one)
    2. ASR              Sarvam Saaras, language auto-detected
    3. graph            planner, live fetch, PostGIS, rules, evidence, capsule
    4. Tamil answer     rendered offline from the capsule by the shipped codebook,
                        no machine translation, then checked by the numeric firewall
    5. answer audio     Sarvam Bulbul TTS

    set -a; . ./.env; set +a; export DHRUVA_DSN=postgresql://...
    PYTHONPATH=backend .venv/bin/python scripts/voice_roundtrip.py --out demo-assets
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import datetime as dt
import logging
import os
import time
import warnings
from pathlib import Path

import httpx

from dhruva.codec.codebook import render
from dhruva.codec.codec import decode, from_base32
from dhruva.evidence.firewall import validate
from dhruva.evidence.schema import EvidenceBundle, EvidenceItem
from dhruva.graph.build import arun

logging.getLogger("copernicusmarine").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Consolidated metadata")

SARVAM = "https://api.sarvam.ai"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
W = 13


def _line(t0: float, step: str, text: str) -> None:
    print(f"[{time.perf_counter() - t0:6.1f} s] {step:<{W}}{text}")


def _more(text: str) -> None:
    print(f"{'':>{10 + W}}{text}")


# The capsule fields the codebook can speak. Quantised onshore by the codec from
# the evidence bundle; the phone has nothing else.
_SPOKEN = (
    "wave_hs_m",
    "wind_kt",
    "wind_dir_deg",
    "curr_kt",
    "curr_dir_deg",
    "sst_c",
    "pfz_dist_nm",
    "bnd_dist_nm",
    "bnd_eta_min",
)


def capsule_bundle(capsule) -> EvidenceBundle:
    """The capsule's own values as a bundle, so the offline sentence can be checked
    against exactly what it was rendered from."""
    return EvidenceBundle(
        items=[
            EvidenceItem(
                key=f, value=float(getattr(capsule, f)), unit="", dataset_id="capsule", cell=""
            )
            for f in _SPOKEN
        ]
    )


async def tts(client: httpx.AsyncClient, key: str, text: str, speaker: str) -> bytes:
    r = await client.post(
        f"{SARVAM}/text-to-speech",
        headers={"api-subscription-key": key},
        json={
            "text": text,
            "target_language_code": "ta-IN",
            "model": "bulbul:v3",
            "speaker": speaker,
            "speech_sample_rate": 22050,
        },
        timeout=60,
    )
    r.raise_for_status()
    return base64.b64decode(r.json()["audios"][0])


async def asr(client: httpx.AsyncClient, key: str, audio: bytes) -> dict:
    r = await client.post(
        f"{SARVAM}/speech-to-text",
        headers={"api-subscription-key": key},
        files={"file": ("question.wav", audio, "audio/wav")},
        data={"model": "saaras:v3", "mode": "transcribe", "language_code": "unknown"},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()


async def main() -> None:
    ap = argparse.ArgumentParser(description="Tamil voice round-trip through DHRUVA.")
    ap.add_argument("--question", default="இப்போது கடலுக்குப் போகலாமா?")
    ap.add_argument("--audio", type=Path, help="a real recording to use instead of TTS")
    ap.add_argument("--lat", type=float, default=11.05)
    ap.add_argument("--lon", type=float, default=79.95)
    ap.add_argument("--test-cyclone-km", type=float, help="TEST INPUT, see trace_query.py")
    ap.add_argument("--out", type=Path, default=Path("."))
    args = ap.parse_args()
    key = os.environ["SARVAM_API_KEY"]
    args.out.mkdir(parents=True, exist_ok=True)

    print(f"DHRUVA voice round-trip   {dt.datetime.now(IST):%d %b %Y %H:%M IST}")
    print("voice: Sarvam (Saaras ASR, Bulbul TTS), standing in until Bhashini is wired")
    if args.test_cyclone_km is not None:
        print(f"TEST INPUT  simulated cyclone warning {args.test_cyclone_km:g} km away")
    print("-" * 96)
    t0 = time.perf_counter()

    async with httpx.AsyncClient() as client:
        if args.audio:
            q_audio = args.audio.read_bytes()
            _line(t0, "question", f"recording {args.audio} ({len(q_audio) // 1024} KB)")
        else:
            q_audio = await tts(client, key, args.question, "anand")
            (args.out / "voice_question_ta.wav").write_bytes(q_audio)
            _line(t0, "question", f"audio synthesised from: {args.question}")
            _more("(TTS stand-in for a fisherman's recording, saved voice_question_ta.wav)")

        heard = await asr(client, key, q_audio)
        transcript = heard["transcript"]
        _line(t0, "ASR", f'heard: "{transcript}"')
        _more(f"language detected: {heard.get('language_code')}")

        state = await arun(
            transcript,
            args.lat,
            args.lon,
            language="ta",
            cyclone_distance_km=args.test_cyclone_km,
        )
        plan = state.get("plan") or {}
        _line(t0, "planner", f"intent {state.get('intent')}  ({plan.get('reason')})")
        for o in state.get("observations", []):
            _more(f"{o.variable.value:<16} {o.value:>7} {o.unit:<7}{o.dataset_id}")
        _line(t0, "risk", f"verdict {str(state.get('risk_class')).upper()}")
        _more(f"rules fired: {', '.join(state.get('fired_rules', [])) or '(none)'}")
        bits = state.get("capsule_bits", "")
        _line(t0, "capsule", f"{bits}  (145 bits)")

        capsule = decode(from_base32(bits))
        answer = render(capsule, "ta")
        live = validate(
            answer, EvidenceBundle.model_validate(state.get("evidence", {})), language="ta"
        )
        own = validate(answer, capsule_bundle(capsule), language="ta")
        _line(t0, "codebook", "Tamil answer rendered offline from the capsule:")
        _more(answer)
        _more(f"firewall vs capsule it was rendered from: {'passed' if own.passed else 'FAILED'}")
        if live.passed:
            _more("firewall vs live evidence: passed")
        else:
            waves = [
                o.value for o in state.get("observations", []) if o.variable.value == "wave_height"
            ]
            _more("firewall vs live evidence: differs, capsule values are quantised")
            _more(
                f"  wave {capsule.wave_hs_m} m on the 0.25 m grid; "
                f"live reading was {waves[0] if waves else '?'} m"
            )

        if not own.passed:
            _line(t0, "TTS", f"NOT SPOKEN: firewall failed {own.messages}")
        else:
            a_audio = await tts(client, key, answer, "anand")
            (args.out / "voice_answer_ta.wav").write_bytes(a_audio)
            _line(
                t0, "TTS", f"answer spoken, saved voice_answer_ta.wav ({len(a_audio) // 1024} KB)"
            )

    print("-" * 96)
    print("Advisory only. Follow official INCOIS and IMD warnings.")


if __name__ == "__main__":
    asyncio.run(main())
