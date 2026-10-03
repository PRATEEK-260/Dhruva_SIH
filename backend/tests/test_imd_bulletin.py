"""IMD bulletins as hazard inputs. A replayed bulletin's centre, read from its
PDF by the same parser as the live feed, sets the cyclone distance and never
speaks for a time it does not cover. Live bulletins in force set it for the
present, an unreadable one forces CAUTION, and with none in force the answer
says so with the time the list was checked."""

import datetime as dt
import hashlib
import json
from pathlib import Path

import pytest

from dhruva.graph.build import _bundle
from dhruva.graph.state import RiskClass, initial_state
from dhruva.risk.rules import assess
from dhruva.sources import imd_bulletin
from dhruva.sources.imd_bulletin import BulletinError, cyclone_source

DATA = Path(__file__).resolve().parents[2] / "data" / "imd" / "bulletins.json"
MICHAUNG = "michaung_nb19"
CENTRE_AT = dt.datetime(2023, 12, 4, 0, tzinfo=dt.UTC)
# The replayed boat, off Chennai (frontend/src/shared/demo.json).
BOAT = (13.0, 80.45)


@pytest.fixture(autouse=True)
def _repo_data(monkeypatch):
    monkeypatch.setattr(imd_bulletin, "_PATH", DATA)


def test_the_replay_reads_its_position_through_the_parser():
    """bulletins.json holds provenance only; the centre comes from the PDF."""
    meta = json.loads(DATA.read_text())[MICHAUNG]
    assert "lat" not in meta and "centre_at" not in meta
    pdf = DATA.parent.parent.parent / meta["local_copy"]
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() == meta["sha256"]
    assert meta["source_url"].startswith("https://rsmcnewdelhi.imd.gov.in/")
    b = imd_bulletin.bulletins()[MICHAUNG]
    assert (b["lat"], b["lon"]) == (13.2, 81.2)
    assert b["centre_at"] == "2023-12-04T00:00:00+00:00"
    assert b["name"] == "MICHAUNG" and b["status"] == "ok"


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
    assert "National Bulletin No. 19 (BOB/06/2023)" in (row.upstream_dataset_id or "")


# ------------------------------------------------------------------ live ----

NOW = dt.datetime(2023, 12, 4, 4, 0, tzinfo=dt.UTC)  # 0930 IST, Michaung in force
CHENNAI_BOAT = (13.0, 80.45)
KOCHI_BOAT = (9.9, 76.0)  # Arabian Sea: a Bay of Bengal storm is not its bulletin


def _feed(*entries, checked=NOW):
    return {
        "checked_at": checked.isoformat(),
        "error": None,
        "bulletins": {str(i): e for i, e in enumerate(entries)},
    }


def _michaung_entry():
    b = imd_bulletin.bulletins()[MICHAUNG]
    return {**b, "local_copy": b["local_copy"], "source_url": b["source_url"]}


def _state(lat, lon, live):
    return initial_state(
        "q",
        lat,
        lon,
        when=NOW,
        cyclone_distance_km=live["cyclone"]["distance_km"] if live["cyclone"] else None,
        cyclone_source=live["cyclone"],
        alerts=live["alerts"],
    )


def test_a_live_cyclone_blocks_a_boat_within_300_km():
    live = imd_bulletin.live_status(*CHENNAI_BOAT, NOW, now=NOW, feed=_feed(_michaung_entry()))
    assert live["status"] == "active"
    # The 0530 IST track point is 4 h from 0930; the 1130 one is 2 h away.
    src = live["cyclone"]
    assert (src["lat"], src["lon"]) == (13.7, 80.9)
    assert src["distance_km"] < 300
    a = assess(_state(*CHENNAI_BOAT, live))
    assert a.risk_class is RiskClass.NO_GO and "CYCLONE-A1" in a.rule_ids
    assert live["bulletins"][0]["source_url"].startswith("https://rsmcnewdelhi.imd.gov.in/")


def test_another_basins_storm_is_not_this_boats_bulletin():
    live = imd_bulletin.live_status(*KOCHI_BOAT, NOW, now=NOW, feed=_feed(_michaung_entry()))
    assert live["status"] == "none" and live["cyclone"] is None and live["alerts"] == []


def test_an_expired_bulletin_is_not_used():
    later = NOW + dt.timedelta(hours=12)  # next issue was 0600 UTC, plus 3 h grace
    live = imd_bulletin.live_status(
        *CHENNAI_BOAT, later, now=later, feed=_feed(_michaung_entry(), checked=later)
    )
    assert live["status"] == "none" and live["cyclone"] is None
    assert live["message"].startswith("No active IMD cyclone bulletin as of 4 Dec 21:30 IST")


def test_a_broken_bulletin_gives_caution_with_its_link_never_safe():
    from dhruva.sources.imd_feed import entry_for

    broken = entry_for(
        b"%PDF-1.7 not a bulletin", "https://rsmcnewdelhi.imd.gov.in/x.pdf", Path("x.pdf"), NOW
    )
    assert broken["status"] == "unreadable"
    live = imd_bulletin.live_status(*CHENNAI_BOAT, NOW, now=NOW, feed=_feed(broken))
    assert live["status"] == "active"
    assert live["message"] == "Official warning: read the IMD bulletin."
    assert live["bulletins"][0]["source_url"] == "https://rsmcnewdelhi.imd.gov.in/x.pdf"
    state = _state(*CHENNAI_BOAT, live)
    state["observations"] = _calm_sea()
    a = assess(state)
    assert a.risk_class is RiskClass.CAUTION and "ALERT-C0" in a.rule_ids


def test_a_far_storm_whose_warning_names_your_coast_is_caution():
    """Over 300 km away, but the fishermen warning names North Tamil Nadu."""
    far_tn_boat = (10.3, 79.9)  # off Point Calimere, ~330 km from the 1130 IST point
    live = imd_bulletin.live_status(*far_tn_boat, NOW, now=NOW, feed=_feed(_michaung_entry()))
    assert live["cyclone"]["distance_km"] > 300
    assert live["alerts"] == [imd_bulletin.ALERT_COAST]
    state = _state(*far_tn_boat, live)
    state["observations"] = _calm_sea()
    assert assess(state).risk_class is RiskClass.CAUTION


def test_no_bulletin_says_so_with_the_check_time():
    live = imd_bulletin.live_status(*CHENNAI_BOAT, NOW, now=NOW, feed=_feed())
    assert live["status"] == "none"
    assert live["message"] == "No active IMD cyclone bulletin as of 4 Dec 09:30 IST."


def test_a_stale_check_says_how_old_it_is():
    live = imd_bulletin.live_status(
        *CHENNAI_BOAT, NOW, now=NOW, feed=_feed(checked=NOW - dt.timedelta(hours=5))
    )
    assert "has not been checked since 4 Dec 04:30 IST" in live["message"]


def test_never_checked_is_not_none():
    live = imd_bulletin.live_status(
        *CHENNAI_BOAT, NOW, now=NOW, feed={"checked_at": None, "bulletins": {}}
    )
    assert live["status"] == "unchecked"


def test_a_past_storm_is_not_judged_by_todays_feed():
    past = NOW - dt.timedelta(days=30)
    live = imd_bulletin.live_status(*CHENNAI_BOAT, past, now=NOW, feed=_feed())
    assert live["status"] == "not_applicable"


def _calm_sea():
    from dhruva.sources.base import Observation
    from dhruva.sources.registry import Variable

    return [
        Observation(
            variable=v,
            value=val,
            unit=u,
            dataset_id="d",
            upstream_dataset_id="u",
            valid_time=NOW,
            cell_lat=13.0,
            cell_lon=80.45,
            requested_lat=13.0,
            requested_lon=80.45,
            grid_resolution_deg=0.083,
            fetched_at=NOW,
        )
        for v, val, u in ((Variable.WAVE_HEIGHT, 0.5, "m"), (Variable.WIND_SPEED, 6.0, "kt"))
    ]
