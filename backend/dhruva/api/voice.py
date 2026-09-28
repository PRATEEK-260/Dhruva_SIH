"""Voice in and out for the phone while it has a signal. Bhashini does both.

At sea the phone does not call this: it plays clips generated here ahead of time
and shipped with the app.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re
from pathlib import Path
from typing import Annotated, Literal

import httpx
from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel, StringConstraints

from dhruva.lang import bhashini

router = APIRouter(tags=["voice"])


# A language code names a cache directory, so it is held to what a code looks
# like: two or three lowercase letters. Anything else (a path, "..") is refused
# before it reaches the filesystem.
LanguageCode = Annotated[str, StringConstraints(pattern=r"^[a-z]{2,3}$")]


class TtsRequest(BaseModel):
    text: Annotated[str, StringConstraints(min_length=1, max_length=2000)]
    language: LanguageCode = "ta"
    gender: Literal["female", "male"] = "female"


class AsrRequest(BaseModel):
    audio_base64: str
    language: LanguageCode = "ta"
    sample_rate: int = 16000


# Every sentence Bhashini has spoken, on disk, so a repeated sentence plays even
# when Bhashini is down (it answers 504 now and then). backend/.voice-cache, both
# from the repo root and in the api container (backend/ is mounted at /app).
VOICE_CACHE = Path(__file__).resolve().parents[2] / ".voice-cache"


def cache_path(text: str, language: str, gender: str) -> Path:
    """The cache file for one sentence. Raises ValueError for a language that
    is not a plain code, so no caller can steer the path out of VOICE_CACHE."""
    if not re.fullmatch(r"[a-z]{2,3}", language):
        raise ValueError(f"not a language code: {language!r}")
    digest = hashlib.sha256(f"{language}|{gender}|{text}".encode()).hexdigest()[:32]
    path = (VOICE_CACHE / language / f"{digest}.wav").resolve()
    if not path.is_relative_to(VOICE_CACHE.resolve()):
        raise ValueError("voice cache path escaped the cache directory")
    return path


def _key() -> str:
    key = os.environ.get("BHASHINI_INFERENCE_API_KEY")
    if not key:
        raise HTTPException(503, "Voice is not configured: BHASHINI_INFERENCE_API_KEY is not set")
    return key


@router.post("/voice/tts")
async def post_tts(req: TtsRequest) -> Response:
    cached = cache_path(req.text, req.language, req.gender)
    if cached.exists():
        return Response(cached.read_bytes(), media_type="audio/wav", headers={"X-Voice": "cache"})
    async with httpx.AsyncClient() as client:
        try:
            audio = await bhashini.tts(client, _key(), req.text, req.language, gender=req.gender)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Bhashini TTS failed: {e}") from e
    cached.parent.mkdir(parents=True, exist_ok=True)
    cached.write_bytes(audio)
    return Response(audio, media_type="audio/wav", headers={"X-Voice": "bhashini"})


@router.post("/voice/asr")
async def post_asr(req: AsrRequest) -> dict[str, str]:
    audio = base64.b64decode(req.audio_base64)
    async with httpx.AsyncClient() as client:
        try:
            text = await bhashini.asr(client, _key(), audio, req.language, req.sample_rate)
        except httpx.HTTPError as e:
            raise HTTPException(502, f"Bhashini ASR failed: {e}") from e
    return {"text": text, "language": req.language}
