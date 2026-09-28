"""The nearest current PFZ line to a boat, from the lines pfz_wfs.py stores.

Only the newest advisory counts, and only while it is fresh: INCOIS issues PFZ
about three times a week, so an advisory more than MAX_AGE_DAYS old has been
superseded and answering from it would send a boat to yesterday's fish.

The answer is described twice: from the boat (distance and bearing to the
closest point of the line), which is what the capsule carries, and from the
nearest landing centre, which is how INCOIS's own text advisories read.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import asdict, dataclass
from typing import Any

import asyncpg

from dhruva.sources.pfz_wfs import CATEGORY_NAMES, MAX_AGE_DAYS

# Beyond this a zone is not "near you"; it is also the capsule's 63 nm rail.
SEARCH_NM = 60.0
M_PER_NM = 1852.0


@dataclass(frozen=True, slots=True)
class NearestPfz:
    uid: str
    issued_for: dt.date
    category: str | None
    # What INCOIS based the line on; None when its data leaves the field empty
    # (the 28 Sep 2026 advisory did). Never filled in by guessing.
    basis: str | None
    state_name: str | None
    distance_nm: float
    bearing_deg: float
    lat: float
    lon: float
    age_days: int
    confidence: int
    source_url: str
    fetched_at: dt.datetime
    centre_name: str | None = None
    centre_distance_nm: float | None = None
    centre_bearing_deg: float | None = None

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["issued_for"] = self.issued_for.isoformat()
        d["fetched_at"] = self.fetched_at.isoformat()
        return d


def freshness(age_days: int) -> int:
    """The capsule's 2-bit pfz_conf. INCOIS publishes no confidence for a line,
    so this carries freshness instead: 3 issued within a day, 2 within two,
    1 within three. The phrasebook speaks a zone only at 2 or more."""
    if age_days <= 1:
        return 3
    if age_days <= 2:
        return 2
    if age_days <= MAX_AGE_DAYS:
        return 1
    return 0


async def nearest_pfz(
    conn: asyncpg.Connection, lat: float, lon: float, on: dt.date
) -> NearestPfz | None:
    """None when there is no fresh advisory, or no line within SEARCH_NM."""
    row = await conn.fetchrow(
        """
        WITH boat AS (SELECT ST_SetSRID(ST_MakePoint($2, $1), 4326) AS g),
        latest AS (
            SELECT max(issued_for) AS d FROM pfz_line
            WHERE issued_for <= $3 AND issued_for >= $3 - $4::int
        )
        SELECT l.uid, l.issued_for, l.category, l.state_name, l.source_url, l.fetched_at,
               ST_Distance(l.geom::geography, boat.g::geography) AS d_m,
               ST_Y(c.cp) AS cp_lat, ST_X(c.cp) AS cp_lon,
               degrees(ST_Azimuth(boat.g::geography, c.cp::geography)) AS az
        FROM pfz_line l
        CROSS JOIN boat
        CROSS JOIN LATERAL (SELECT ST_ClosestPoint(l.geom, boat.g) AS cp) c
        WHERE l.issued_for = (SELECT d FROM latest)
        ORDER BY l.geom::geography <-> boat.g::geography
        LIMIT 1
        """,
        lat,
        lon,
        on,
        MAX_AGE_DAYS,
    )
    if row is None or row["d_m"] / M_PER_NM > SEARCH_NM:
        return None

    centre = await conn.fetchrow(
        """
        WITH p AS (SELECT ST_SetSRID(ST_MakePoint($2, $1), 4326) AS g)
        SELECT name,
               ST_Distance(lc.geom::geography, p.g::geography) AS d_m,
               degrees(ST_Azimuth(lc.geom::geography, p.g::geography)) AS az
        FROM landing_centre lc CROSS JOIN p
        ORDER BY lc.geom::geography <-> p.g::geography
        LIMIT 1
        """,
        row["cp_lat"],
        row["cp_lon"],
    )

    age = (on - row["issued_for"]).days
    return NearestPfz(
        uid=row["uid"],
        issued_for=row["issued_for"],
        category=row["category"],
        basis=CATEGORY_NAMES.get(row["category"], row["category"]) if row["category"] else None,
        state_name=row["state_name"],
        distance_nm=round(row["d_m"] / M_PER_NM, 2),
        # A boat sitting on the line has no direction to it; call it north.
        bearing_deg=round(row["az"] or 0.0, 1),
        lat=row["cp_lat"],
        lon=row["cp_lon"],
        age_days=age,
        confidence=freshness(age),
        source_url=row["source_url"],
        fetched_at=row["fetched_at"],
        centre_name=centre["name"] if centre else None,
        centre_distance_nm=round(centre["d_m"] / M_PER_NM, 1) if centre else None,
        centre_bearing_deg=round(centre["az"], 0) if centre and centre["az"] is not None else None,
    )
