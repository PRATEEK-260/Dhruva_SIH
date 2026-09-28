"""Bhashini ASR, translation and TTS through the Dhruva inference pipeline.

The Udyat dashboard issues an inference API key that goes straight into the
``Authorization`` header of the pipeline endpoint, so the config-then-compute handshake
(ULCA user ID + API key → endpoint + key) is not needed for these calls.

Service IDs are the AI4Bharat models hosted on Dhruva. Dravidian languages and the
Indo-Aryan ones are served by different ASR and TTS models; ``_family`` picks one.
"""

from __future__ import annotations

import asyncio
import base64
import io
import os
import struct
import wave

import httpx
import numpy as np

PIPELINE = os.environ.get(
    "BHASHINI_INFERENCE_URL", "https://dhruva-api.bhashini.gov.in/services/inference/pipeline"
)

_DRAVIDIAN = {"ta", "te", "kn", "ml"}
TRANSLATION = "ai4bharat/indictrans-v2-all-gpu--t4"


def _family(language: str) -> str:
    return "dravidian" if language in _DRAVIDIAN else "indo_aryan"


def _asr_service(language: str) -> str:
    return f"ai4bharat/conformer-multilingual-{_family(language)}-gpu--t4"


def _tts_service(language: str) -> str:
    return f"ai4bharat/indic-tts-coqui-{_family(language)}-gpu--t4"


async def _call(
    client: httpx.AsyncClient, key: str, task: dict, data: dict, attempts: int = 3
) -> dict:
    """One pipeline task. The hosted models answer 504 now and then (Odia TTS most
    often), and a second try usually lands, so 5xx is retried."""
    body = {"pipelineTasks": [task], "inputData": data}
    for attempt in range(attempts):
        last = attempt == attempts - 1
        try:
            r = await client.post(PIPELINE, headers={"Authorization": key}, json=body, timeout=60)
        except httpx.TimeoutException:
            if last:
                raise
        else:
            if r.status_code < 500 or last:
                r.raise_for_status()
                return r.json()["pipelineResponse"][0]
        await asyncio.sleep(1 + attempt)
    raise AssertionError("unreachable")


async def asr(
    client: httpx.AsyncClient, key: str, audio: bytes, language: str, sample_rate: int
) -> str:
    """Transcribe a WAV recording. The language is given, not detected."""
    out = await _call(
        client,
        key,
        {
            "taskType": "asr",
            "config": {
                "language": {"sourceLanguage": language},
                "serviceId": _asr_service(language),
                "audioFormat": "wav",
                "samplingRate": sample_rate,
            },
        },
        {"audio": [{"audioContent": base64.b64encode(audio).decode()}]},
    )
    return out["output"][0]["source"]


async def translate(
    client: httpx.AsyncClient, key: str, text: str, source: str, target: str
) -> str:
    out = await _call(
        client,
        key,
        {
            "taskType": "translation",
            "config": {
                "language": {"sourceLanguage": source, "targetLanguage": target},
                "serviceId": TRANSLATION,
            },
        },
        {"input": [{"source": text}]},
    )
    return out["output"][0]["target"]


async def tts(
    client: httpx.AsyncClient,
    key: str,
    text: str,
    language: str,
    gender: str = "female",
    sample_rate: int = 22050,
) -> bytes:
    """Speak ``text``; returns WAV bytes."""
    out = await _call(
        client,
        key,
        {
            "taskType": "tts",
            "config": {
                "language": {"sourceLanguage": language},
                "serviceId": _tts_service(language),
                "gender": gender,
                "samplingRate": sample_rate,
            },
        },
        {"input": [{"source": text}]},
    )
    return to_pcm16(base64.b64decode(out["audio"][0]["audioContent"]))


def to_pcm16(wav: bytes) -> bytes:
    """Bhashini TTS returns 32-bit float WAV, which Python's ``wave`` module and some
    players reject. Re-encode as 16-bit PCM; PCM input comes back unchanged."""
    fmt = wav.find(b"fmt ")
    audio_format, channels, rate = struct.unpack_from("<HHI", wav, fmt + 8)
    if audio_format != 3:
        return wav
    data = wav.find(b"data")
    (size,) = struct.unpack_from("<I", wav, data + 4)
    samples = np.frombuffer(wav, dtype="<f4", count=size // 4, offset=data + 8)
    pcm = (np.clip(samples, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()
