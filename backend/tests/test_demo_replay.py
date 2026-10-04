"""Recorded runs: how a request finds its recording, and that a replay is always
labelled. The whole value of a recording is that it is a real run; a replay the
screen cannot tell apart from a live answer would be a fake one."""

import datetime as dt
import json

import pytest
from fastapi.testclient import TestClient

from dhruva.app import app
from dhruva.demo import replay
from dhruva.demo.boats import DEMO_BOATS

NOW = dt.datetime(2026, 9, 28, 12, 0, tzinfo=dt.UTC)


class TestKeys:
    def test_now_and_tomorrow_morning_match_by_ist_hour(self):
        assert replay.when_key(None, NOW) == "now"
        five_am_ist = dt.datetime(2026, 9, 28, 23, 30, tzinfo=dt.UTC)
        assert replay.when_key(five_am_ist, NOW) == "ist05"
        # The same departure asked a day later still matches.
        assert (
            replay.when_key(five_am_ist + dt.timedelta(days=1), NOW + dt.timedelta(days=1))
            == "ist05"
        )

    def test_a_past_storm_matches_on_its_own_date(self):
        michaung = dt.datetime(2023, 12, 4, tzinfo=dt.UTC)
        assert replay.when_key(michaung, NOW) == "2023-12-04T00"

    def test_query_case_and_spacing_do_not_matter(self):
        a = replay.key(
            "Is there  a Cyclone warning?", "ta", 11.05, 79.95, "frp_under_12m", None, None
        )
        b = replay.key(
            "is there a cyclone warning?", "ta", 11.0501, 79.9499, "frp_under_12m", None, None
        )
        assert a == b

    def test_language_boat_class_and_test_input_all_separate_recordings(self):
        base = ("q", "ta", 11.05, 79.95, "frp_under_12m", None, None)
        k = replay.key(*base)
        assert k != replay.key("q", "en", 11.05, 79.95, "frp_under_12m", None, None)
        assert k != replay.key("q", "ta", 11.05, 79.95, "mechanised_12_20m", None, None)
        assert k != replay.key("q", "ta", 11.05, 79.95, "frp_under_12m", None, 180)


class TestMode:
    def test_default_is_fallback_and_junk_is_ignored(self, monkeypatch):
        monkeypatch.delenv("DHRUVA_DEMO", raising=False)
        assert replay.mode() == "fallback"
        monkeypatch.setenv("DHRUVA_DEMO", "sometimes")
        assert replay.mode() == "fallback"
        monkeypatch.setenv("DHRUVA_DEMO", "REPLAY")
        assert replay.mode() == "replay"

    def test_live_failed_only_when_nothing_was_observed(self):
        assert replay.live_failed({"observations": [], "errors": ["timeout"]})
        assert not replay.live_failed({"observations": ["x"], "errors": ["timeout"]})
        assert not replay.live_failed({"observations": [], "errors": []})


@pytest.fixture
def recorded(tmp_path, monkeypatch):
    k = replay.key("recorded question", "ta", 11.05, 79.95, "frp_under_12m", None, None)
    entry = {
        "narration": "SAFE",
        "risk_class": "safe",
        "firewall_passed": True,
        "evidence": {"items": []},
        "capsule_base32": "AIMTA3YDQAAAAAIQAAMRB7AAABNUIAA",
        "reason_code": 0,
        "notice": "Advisory only. Follow official INCOIS and IMD warnings.",
        "recorded_at": "2026-09-28T12:40:00+00:00",
    }
    path = tmp_path / "recordings.json"
    path.write_text(json.dumps({"recorded_at": entry["recorded_at"], "entries": {k: entry}}))
    return path


def test_replay_mode_serves_the_recording_and_labels_it(recorded, monkeypatch):
    monkeypatch.setenv("DHRUVA_DEMO", "replay")
    monkeypatch.setattr(replay, "find", _finder(recorded))
    r = TestClient(app).post(
        "/advisory",
        json={
            "query": "Recorded  Question",
            "lat": 11.05,
            "lon": 79.95,
            "language": "ta",
            "log": False,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["recorded_at"] == "2026-09-28T12:40:00+00:00"
    assert body["replay_reason"] == "demo mode"


def test_off_mode_never_replays(recorded, monkeypatch):
    monkeypatch.setenv("DHRUVA_DEMO", "off")
    calls = []

    def spy(k):
        calls.append(k)
        return _finder(recorded)(k)

    monkeypatch.setattr(replay, "find", spy)

    async def boom(*a, **kw):
        raise RuntimeError("live run failed")

    monkeypatch.setattr("dhruva.api.advisory.arun", boom)
    r = TestClient(app, raise_server_exceptions=False).post(
        "/advisory",
        json={
            "query": "recorded question",
            "lat": 11.05,
            "lon": 79.95,
            "language": "ta",
            "log": False,
        },
    )
    assert r.status_code == 502
    assert calls == []


def test_fallback_mode_replays_only_when_live_fails(recorded, monkeypatch):
    monkeypatch.setenv("DHRUVA_DEMO", "fallback")
    monkeypatch.setattr(replay, "find", _finder(recorded))

    async def boom(*a, **kw):
        raise RuntimeError("live run failed")

    monkeypatch.setattr("dhruva.api.advisory.arun", boom)
    r = TestClient(app).post(
        "/advisory",
        json={
            "query": "recorded question",
            "lat": 11.05,
            "lon": 79.95,
            "language": "ta",
            "log": False,
        },
    )
    assert r.status_code == 200
    assert r.json()["replay_reason"] == "live sources failed"


def _finder(path):
    """replay.find, reading the test's recordings file instead of data/demo/."""
    real_find = replay.find
    return lambda k: real_find(k, path)


def test_every_demo_boat_is_named_and_inside_the_capsule_grid():
    from dhruva.codec.fields import ZONE_LAT_MAX, ZONE_LAT_MIN, ZONE_LON_MAX, ZONE_LON_MIN

    assert len({b["name"] for b in DEMO_BOATS}) == len(DEMO_BOATS)
    for b in DEMO_BOATS:
        assert ZONE_LAT_MIN <= b["lat"] < ZONE_LAT_MAX
        assert ZONE_LON_MIN <= b["lon"] < ZONE_LON_MAX


def test_a_question_whose_own_answer_failed_plays_the_recording():
    """On a server with Copernicus off, query #7 answers No data while the
    weather still answers; the labelled recording is the more useful reply."""
    from dhruva.demo.replay import live_failed

    errors = ["copernicus_globcolour_my: RuntimeError"]
    weather = ["wave_height"]
    assert live_failed(
        {"observations": weather, "errors": errors, "decline_answer": {"status": "no_data"}}
    )
    assert live_failed({"observations": weather, "errors": errors, "answer": {"status": "no_data"}})
    assert not live_failed(
        {"observations": weather, "errors": errors, "decline_answer": {"status": "ok"}}
    )
    assert not live_failed(
        {"observations": weather, "errors": [], "decline_answer": {"status": "no_data"}}
    )


def test_copernicus_off_fails_the_fetch_without_importing(monkeypatch):
    import pytest

    from dhruva.sources.copernicus import fetch_grid

    monkeypatch.setenv("DHRUVA_COPERNICUS", "off")
    with pytest.raises(RuntimeError, match="off on this server"):
        fetch_grid("x", ["CHL"], lat_min=0, lat_max=1, lon_min=0, lon_max=1, start=None, end=None)  # type: ignore[arg-type]
