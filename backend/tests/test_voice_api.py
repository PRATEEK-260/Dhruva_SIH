"""The voice cache is keyed by language on disk, so a language that is not a
plain code must never reach the filesystem (commit security review, 2026-09-29)."""

import pytest
from fastapi.testclient import TestClient

from dhruva.api.voice import VOICE_CACHE, cache_path
from dhruva.app import app


@pytest.mark.parametrize("language", ["../../etc", "..", "ta/../../x", "TA", "tamil", "", "t"])
def test_a_path_or_non_code_language_is_refused_by_the_api(language, monkeypatch):
    monkeypatch.setenv("BHASHINI_INFERENCE_API_KEY", "unused")
    r = TestClient(app).post("/voice/tts", json={"text": "x", "language": language})
    assert r.status_code == 422


def test_gender_is_one_of_two():
    r = TestClient(app).post("/voice/tts", json={"text": "x", "language": "ta", "gender": "../x"})
    assert r.status_code == 422


@pytest.mark.parametrize("language", ["../../etc", "..", "ta/.."])
def test_cache_path_refuses_a_path_directly(language):
    with pytest.raises(ValueError):
        cache_path("x", language, "female")


def test_a_real_code_stays_inside_the_cache():
    assert cache_path("hello", "ta", "female").is_relative_to(VOICE_CACHE.resolve())
