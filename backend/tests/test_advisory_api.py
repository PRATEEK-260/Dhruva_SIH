"""POST /advisory is the one new door onto the graph. These tests care about
the contract: a bad boat_class is rejected before anything runs, the response
shape matches what the frontend needs, and the capsule the response carries
actually decodes to the risk_class the response also carries — the same
band-coherence property backend/tests/test_graph_codec.py holds for node 9
directly, held here across the HTTP boundary too.
"""

from fastapi.testclient import TestClient

from dhruva.app import create_app
from dhruva.codec.codebook import split_reason
from dhruva.codec.codec import decode, from_base32
from dhruva.codec.fields import RISK_CLASSES

client = TestClient(create_app())


def test_advisory_rejects_a_bad_boat_class():
    r = client.post(
        "/advisory",
        json={"query": "can I go out?", "lat": 11.05, "lon": 79.95, "boat_class": "rowboat"},
    )
    assert r.status_code == 422


def test_advisory_returns_the_full_shape():
    r = client.post("/advisory", json={"query": "can I go out?", "lat": 11.05, "lon": 79.95})
    assert r.status_code == 200
    body = r.json()
    for key in (
        "narration",
        "risk_class",
        "firewall_passed",
        "evidence",
        "capsule_base32",
        "reason_code",
        "notice",
    ):
        assert key in body, key


def test_advisory_notice_is_always_the_fixed_line():
    from dhruva.app import ADVISORY_NOTICE

    r = client.post("/advisory", json={"query": "can I go out?", "lat": 11.05, "lon": 79.95})
    assert r.json()["notice"] == ADVISORY_NOTICE


def test_advisory_capsule_band_matches_the_response_risk_class():
    r = client.post("/advisory", json={"query": "can I go out?", "lat": 11.05, "lon": 79.95})
    body = r.json()
    capsule = decode(from_base32(body["capsule_base32"]))
    band, _family, _modifier = split_reason(capsule.reason_code)
    assert RISK_CLASSES[band] == body["risk_class"]


def test_advisory_recent_is_reachable():
    r = client.get("/advisory/recent")
    assert r.status_code == 200
    assert isinstance(r.json(), list)


def test_advisory_with_log_false_never_touches_the_request_log(monkeypatch):
    import dhruva.api.advisory as advisory

    async def fake_arun(*_args, **_kw):
        return {"narration": "x", "evidence": {}, "capsule_bits": "", "reason_code": 0}

    async def must_not_connect():
        raise AssertionError("log=false must not open the request log")

    monkeypatch.setattr(advisory, "arun", fake_arun)
    monkeypatch.setattr(advisory, "_connect", must_not_connect)
    r = client.post(
        "/advisory", json={"query": "conditions", "lat": 11.05, "lon": 79.95, "log": False}
    )
    assert r.status_code == 200


def test_advisory_passes_when_through_to_the_request_log(monkeypatch):
    import datetime as dt

    import dhruva.api.advisory as advisory

    seen: dict = {}

    async def fake_arun(*_args, **kw):
        seen["when"] = kw["when"]
        return {"narration": "x", "evidence": {}, "capsule_bits": "", "reason_code": 0}

    class FakeConn:
        async def close(self):
            pass

    async def fake_connect():
        return FakeConn()

    async def noop(*_a, **_kw):
        pass

    async def capture_insert(_conn, **kw):
        seen["logged"] = kw["valid_for"]

    monkeypatch.setattr(advisory, "arun", fake_arun)
    monkeypatch.setattr(advisory, "_connect", fake_connect)
    monkeypatch.setattr(advisory, "apply_schema", noop)
    monkeypatch.setattr(advisory, "insert_advisory", capture_insert)
    r = client.post(
        "/advisory",
        json={"query": "q", "lat": 13.0, "lon": 73.5, "when": "2026-08-01T06:00:00Z"},
    )
    assert r.status_code == 200
    expected = dt.datetime(2026, 8, 1, 6, tzinfo=dt.UTC)
    assert seen["when"] == expected
    assert seen["logged"] == expected
