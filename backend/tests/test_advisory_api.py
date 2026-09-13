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
