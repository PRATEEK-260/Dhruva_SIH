"""A stored IMD bulletin: its centre, not a test input, sets the cyclone distance,
and it never speaks for a time it does not cover."""

import datetime as dt
import json
from pathlib import Path

import pytest

from dhruva.graph.build import _bundle
from dhruva.graph.state import RiskClass, initial_state
from dhruva.risk.rules import assess
from dhruva.sources import imd_bulletin
from dhruva.sources.imd_bulletin import BulletinError, cyclone_source

DATA = Path(__file__).resolve().parents[2] / "data" / "imd" / "bulletins.json"
MICHAUNG = "rsmc_michaung_adv9"
CENTRE_AT = dt.datetime(2023, 12, 4, 0, tzinfo=dt.UTC)
# The replayed boat, off Chennai (frontend/src/shared/demo.json).
BOAT = (13.0, 80.45)


@pytest.fixture(autouse=True)
def _repo_data(monkeypatch):
    monkeypatch.setattr(imd_bulletin, "_PATH", DATA)


def test_the_record_matches_the_advisory():
    b = json.loads(DATA.read_text())[MICHAUNG]
    assert (b["lat"], b["lon"]) == (13.2, 81.2)
    assert b["centre_at"] == "2023-12-04T00:00:00Z"
    assert b["source_url"].startswith("https://rsmcnewdelhi.imd.gov.in/")
    assert (DATA.parent.parent.parent / b["local_copy"]).exists()


def test_distance_is_worked_out_from_imd_centre():
    src = cyclone_source(MICHAUNG, *BOAT, CENTRE_AT)
    # 0.2 deg north and 0.75 deg east at 13 N: about 84 km.
    assert 80 < src["distance_km"] < 88


def test_the_bulletin_refuses_another_day():
    with pytest.raises(BulletinError):
        cyclone_source(MICHAUNG, *BOAT, CENTRE_AT + dt.timedelta(days=1))
    with pytest.raises(BulletinError):
        cyclone_source(MICHAUNG, *BOAT, None)
    with pytest.raises(BulletinError):
        cyclone_source("made_up", *BOAT, CENTRE_AT)


def test_the_evidence_row_names_imd_not_the_engine():
    src = cyclone_source(MICHAUNG, *BOAT, CENTRE_AT)
    state = initial_state(
        "q", *BOAT, when=CENTRE_AT, cyclone_distance_km=src["distance_km"], cyclone_source=src
    )
    a = assess(state)
    assert a.risk_class is RiskClass.NO_GO
    assert "CYCLONE-A1" in a.rule_ids
    rows = [i for i in _bundle(state, a).items if i.key == "cyclone_distance"]
    assert len(rows) == 1
    row = rows[0]
    assert row.dataset_id == "imd_rsmc_bulletin"
    assert row.rule_id == "CYCLONE-A1" and row.threshold == 300
    assert row.valid_time == CENTRE_AT
    assert "Advisory No. 9" in (row.upstream_dataset_id or "")
