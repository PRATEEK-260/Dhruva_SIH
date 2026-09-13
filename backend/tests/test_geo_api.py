"""Every rendered EEZ/IMBL/MPA line carries the indicative flag (CLAUDE.md);
every PFZ row carries source_url and fetched_at. These are the two facts a
judge or a fisherman could otherwise mistake for more authority than the data
has, so they are pinned here rather than trusted to the frontend alone.
"""

import pytest
from fastapi.testclient import TestClient

from dhruva.app import create_app

client = TestClient(create_app())


def _get_or_skip(path: str):
    r = client.get(path)
    if r.status_code == 503:
        pytest.skip("database not reachable")
    return r


def test_boundaries_is_a_feature_collection_with_indicative_flags():
    r = _get_or_skip("/geo/boundaries")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    for feature in body["features"]:
        assert feature["properties"]["indicative"] is True


def test_zones_is_a_feature_collection_with_indicative_flags():
    r = _get_or_skip("/geo/zones")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    for feature in body["features"]:
        assert feature["properties"]["indicative"] is True


def test_pfz_carries_source_url_and_fetched_at_on_every_feature():
    r = _get_or_skip("/geo/pfz")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    for feature in body["features"]:
        assert feature["properties"]["source_url"]
        assert feature["properties"]["fetched_at"]
