"""The IMD National Bulletin parser, against real bulletins (text extracted
from the PDFs on rsmcnewdelhi.imd.gov.in into tests/fixtures/imd/).

What a misread would cost: a centre in the wrong place moves the 300 km
override, a missed category drops a depression's warning, and a parse that
quietly fails reads as calm. So every field the risk engine uses is pinned to
what the bulletin says, and a bulletin with no readable body must come back
unreadable, not empty."""

import datetime as dt
from pathlib import Path

import pytest

from dhruva.sources.imd_parser import CYCLONES, DISTURBANCES, normalise, parse_pdf, parse_text

FIXTURES = Path(__file__).parent / "fixtures" / "imd"
UTC = dt.UTC


def _parse(name: str):
    return parse_text((FIXTURES / name).read_text(encoding="utf-8"))


def test_at_least_five_real_bulletins_including_michaung_and_a_depression():
    names = sorted(p.name for p in FIXTURES.glob("*.txt"))
    assert len(names) >= 5
    assert any("michaung" in n for n in names)
    assert any("depression" in n for n in names)


class TestMichaung:
    """National Bulletin No. 19 (BOB/06/2023), 0845 IST 4 Dec 2023."""

    b = _parse("bob06_2023_no19_michaung_cs.txt")

    def test_identity(self):
        assert self.b.status == "ok", self.b.missing
        assert (self.b.number, self.b.system_id, self.b.basin) == (19, "BOB/06/2023", "BOB")
        assert self.b.name == "MICHAUNG"
        assert self.b.category == "Cyclonic Storm" and self.b.category in CYCLONES

    def test_centre_and_times_in_utc(self):
        assert (self.b.lat, self.b.lon) == (13.2, 81.2)
        assert self.b.centre_at == dt.datetime(2023, 12, 4, 0, 0, tzinfo=UTC)  # 0530 IST
        assert self.b.issued_at == dt.datetime(2023, 12, 4, 3, 15, tzinfo=UTC)  # 0845 IST
        assert self.b.next_issue_at == dt.datetime(2023, 12, 4, 6, 0, tzinfo=UTC)

    def test_forecast_track(self):
        assert len(self.b.track) == 8
        first, last = self.b.track[0], self.b.track[-1]
        assert (first.lat, first.lon, first.category) == (13.2, 81.2, "Cyclonic Storm")
        assert first.wind_kmph == (80, 90) and first.gust_kmph == 100
        assert self.b.track[1].category == "Severe Cyclonic Storm"
        assert (last.lat, last.lon, last.category) == (17.8, 81.8, "Depression")
        assert last.at == dt.datetime(2023, 12, 6, 12, 0, tzinfo=UTC)

    def test_fishermen_warning_names_tamil_nadu(self):
        w = self.b.fishermen_warning or ""
        assert w.startswith("Fishermen are advised not to venture")
        assert "North Tamil Nadu-Puducherry" in w


@pytest.mark.parametrize(
    "name,number,system,category,centre",
    [
        (
            "bob06_2023_no21_michaung_scs.txt",
            21,
            "BOB/06/2023",
            "Severe Cyclonic Storm",
            (13.5, 80.8),
        ),
        ("bob06_2026_no15_deep_depression.txt", 15, "BOB/06/2026", "Deep Depression", (18.5, 83.5)),
        ("bob07_2026_no06_depression.txt", 6, "BOB/07/2026", "Depression", (18.9, 96.0)),
        ("bob07_2026_no01_depression_no_table.txt", 1, "BOB/07/2026", "Depression", (15.6, 97.6)),
    ],
)
def test_disturbances_parse(name, number, system, category, centre):
    b = _parse(name)
    assert b.status == "ok", b.missing
    assert (b.number, b.system_id, b.category) == (number, system, category)
    assert (b.lat, b.lon) == centre
    assert b.category in DISTURBANCES
    assert b.centre_at is not None and b.issued_at is not None
    assert b.fishermen_warning and "not to venture" in b.fishermen_warning


def test_a_bulletin_without_a_table_takes_its_centre_from_the_text():
    b = _parse("bob07_2026_no01_depression_no_table.txt")
    assert b.track == []
    assert b.centre_at == dt.datetime(2026, 9, 28, 0, 0, tzinfo=UTC)  # 0530 IST
    assert b.next_issue_at == dt.datetime(2026, 9, 28, 7, 0, tzinfo=UTC)  # 1230 IST


def test_a_weakened_system_is_a_low_with_no_centre():
    """'weakened in to a Well Marked Low': no longer a disturbance, so no
    override; its fishermen warning is still read."""
    b = _parse("bob07_2026_no11_wml.txt")
    assert b.status == "ok"
    assert b.category == "Well Marked Low Pressure Area"
    assert b.category not in DISTURBANCES
    assert b.lat is None and b.next_issue_at is None
    assert "not to venture" in (b.fishermen_warning or "")


def test_a_bulletin_with_no_body_text_is_not_read_as_calm():
    """No. 29 of BOB/06/2026: its header extracts, its body does not."""
    b = _parse("bob06_2026_no29_no_body_text.txt")
    assert b.status == "partial"
    assert "category" in b.missing
    assert b.fishermen_warning is None


def test_a_broken_pdf_is_unreadable_not_an_exception():
    b = parse_pdf(b"%PDF-1.7\n this is not a bulletin \n%%EOF")
    assert b.status == "unreadable"
    assert parse_pdf(b"").status == "unreadable"


def test_empty_text_is_unreadable():
    assert parse_text("").status == "unreadable"


def test_normalise_mends_the_pdf_breakage():
    t = normalise("near Latitude 15. 6°N and Long itude 97.6°E")
    assert "Latitude 15.6°N and Longitude 97.6°E" in t


def test_a_disturbance_without_a_centre_is_partial():
    text = (FIXTURES / "bob07_2026_no06_depression.txt").read_text(encoding="utf-8")
    text = text.replace("latitude", "lat.").replace("18.9/96.0", "")
    b = parse_text(text)
    assert b.category == "Depression"
    assert "centre" in b.missing and b.status == "partial"
