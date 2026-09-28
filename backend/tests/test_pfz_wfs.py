"""INCOIS PFZ lines from the geoportal WFS, and the nearest-line lookup.

The parser tests use the exact property names INCOIS's pfzlines layer returned
on 28 Sep 2026. The database tests need PostGIS with the lines loaded
(python -m dhruva.sources.pfz_wfs) and skip otherwise. They pin what matters for
a boat: a stale advisory must never be offered as today's, and the capsule must
carry a zone that is really there.
"""

import datetime as dt
import os

import asyncpg
import pytest

from dhruva.codec.codec import decode, from_base32
from dhruva.evidence.schema import pfz_item
from dhruva.geo.pfz import SEARCH_NM, freshness, nearest_pfz
from dhruva.sources.pfz_wfs import MAX_AGE_DAYS, julian_to_date, parse_centres, parse_lines

DSN = (
    f"postgresql://dhruva:{os.environ.get('POSTGRES_PASSWORD', '')}"
    f"@localhost:{os.environ.get('POSTGRES_HOST_PORT', '55432')}/dhruva"
)
DEMO_LAT, DEMO_LON = 11.05, 79.95

LINE = {
    "type": "Feature",
    "geometry": {
        "type": "MultiLineString",
        "coordinates": [[[80.2169, 10.6712], [80.2174, 10.6713]]],
    },
    "properties": {
        "Category": "chl",
        "State_Name": "NORTH TAMILNADU",
        "Julian_day": "270",
        "Sno": "001",
        "Year": 2026,
        "UID": "2026270001",
    },
}

CENTRE = {
    "type": "Feature",
    "geometry": {"type": "Point", "coordinates": [79.85, 10.77]},
    "properties": {
        "SECTOR_NAM": "NORTH TAMILNADU",
        "DIST_NAME": "Nagappattinam",
        "LC_NAME": "Nagapattinam Harbour",
        "LC_UNIQUE_": "TN0001",
    },
}


class TestParsing:
    def test_julian_day_270_of_2026_is_27_september(self):
        assert julian_to_date(2026, 270) == dt.date(2026, 9, 27)
        assert julian_to_date(2024, 366) == dt.date(2024, 12, 31)
        with pytest.raises(ValueError):
            julian_to_date(2026, 0)

    def test_a_line_keeps_its_date_uid_and_basis(self):
        (line,) = parse_lines({"features": [LINE]})
        assert line.uid == "2026270001"
        assert line.issued_for == dt.date(2026, 9, 27)
        assert line.category == "chl"
        assert line.state_name == "North Tamilnadu"
        assert line.geometry["type"] == "MultiLineString"

    def test_an_undated_line_is_dropped_not_guessed(self):
        undated = {**LINE, "properties": {**LINE["properties"], "Julian_day": None}}
        assert parse_lines({"features": [undated]}) == []

    def test_a_single_linestring_is_promoted(self):
        single = {
            **LINE,
            "geometry": {"type": "LineString", "coordinates": [[80.2, 10.6], [80.3, 10.7]]},
        }
        (line,) = parse_lines({"features": [single]})
        assert line.geometry == {
            "type": "MultiLineString",
            "coordinates": [[[80.2, 10.6], [80.3, 10.7]]],
        }

    def test_landing_centre_is_lon_lat_in_geojson(self):
        (c,) = parse_centres({"features": [CENTRE]})
        assert (c.lat, c.lon) == (10.77, 79.85)
        assert c.name == "Nagapattinam Harbour"


class TestFreshness:
    def test_confidence_falls_with_age_and_stops_at_the_limit(self):
        assert [freshness(d) for d in range(MAX_AGE_DAYS + 2)] == [3, 3, 2, 1, 0]

    def test_the_phrasebook_speaks_a_one_day_old_zone(self):
        # structure.yaml: pfz_min_confidence 2
        assert freshness(1) >= 2


class TestEvidence:
    def test_pfz_row_carries_source_date_and_cell(self):
        item = pfz_item(
            {
                "distance_nm": 15.3,
                "uid": "2026270002",
                "lat": 11.069,
                "lon": 80.208,
                "issued_for": "2026-09-27",
            }
        )
        assert (item.key, item.value, item.unit, item.dataset_id) == (
            "pfz_distance",
            15.3,
            "nm",
            "incois_pfz",
        )
        assert item.valid_time is not None and item.valid_time.date() == dt.date(2026, 9, 27)
        assert "2026270002" in (item.upstream_dataset_id or "")


async def _conn() -> asyncpg.Connection | None:
    try:
        return await asyncpg.connect(DSN, timeout=5)
    except Exception:
        return None


async def _latest(conn: asyncpg.Connection) -> dt.date | None:
    try:
        return await conn.fetchval("SELECT max(issued_for) FROM pfz_line")
    except asyncpg.UndefinedTableError:
        return None


class TestAgainstDatabase:
    async def test_nearest_line_is_within_reach_and_described_from_a_centre(self):
        conn = await _conn()
        if conn is None:
            pytest.skip("database not reachable")
        try:
            latest = await _latest(conn)
            if latest is None:
                pytest.skip("PFZ lines not loaded")
            pfz = await nearest_pfz(conn, DEMO_LAT, DEMO_LON, latest)
            if pfz is None:
                pytest.skip("no line near the demo point in the loaded advisory")
            assert 0 <= pfz.distance_nm <= SEARCH_NM
            assert 0 <= pfz.bearing_deg < 360
            assert pfz.issued_for == latest
            assert pfz.confidence == 3
            assert pfz.centre_name
            assert pfz.source_url.startswith("https://incois.gov.in/")
        finally:
            await conn.close()

    async def test_a_stale_advisory_is_never_offered(self):
        conn = await _conn()
        if conn is None:
            pytest.skip("database not reachable")
        try:
            latest = await _latest(conn)
            if latest is None:
                pytest.skip("PFZ lines not loaded")
            later = latest + dt.timedelta(days=MAX_AGE_DAYS + 1)
            assert await nearest_pfz(conn, DEMO_LAT, DEMO_LON, later) is None
        finally:
            await conn.close()

    async def test_an_advisory_is_not_used_before_it_was_issued(self):
        conn = await _conn()
        if conn is None:
            pytest.skip("database not reachable")
        try:
            latest = await _latest(conn)
            if latest is None:
                pytest.skip("PFZ lines not loaded")
            earlier = await conn.fetchval("SELECT min(issued_for) FROM pfz_line")
            assert earlier is not None
            assert (
                await nearest_pfz(conn, DEMO_LAT, DEMO_LON, earlier - dt.timedelta(days=1)) is None
            )
        finally:
            await conn.close()


def test_capsule_round_trips_a_pfz():
    """What the codec node writes, the phone reads back: distance to the nm and
    bearing to the 16-point compass."""
    from dhruva.codec.codec import Capsule, encode, to_base32

    c = Capsule(
        msg_type="advisory",
        lat=DEMO_LAT,
        lon=DEMO_LON,
        risk_class="safe",
        pfz_bearing_deg=85.7,
        pfz_dist_nm=15,
        pfz_conf=3,
    )
    back = decode(from_base32(to_base32(encode(c))))
    assert (back.pfz_dist_nm, back.pfz_bearing_deg, back.pfz_conf) == (15, 90.0, 3)
