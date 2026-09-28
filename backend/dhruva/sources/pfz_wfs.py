"""INCOIS potential-fishing-zone lines, from the WFS behind INCOIS's own geoportal.

INCOIS publishes no PFZ API. Its public geoportal
(https://incois.gov.in/geoportal/MFASPFZ/index.html) draws the day's PFZ lines
from two WFS layers on INCOIS's GeoServer, and this reads the same two:

    PFZ_Automation:pfzlines                      the lines, one set per advisory
    PFZ_LandingCentres:LandingCenters_29Apr2024  the 1223 landing centres

So this is still "scraped and attributed" (CLAUDE.md): a public map service
read the way the portal reads it, with the source URL and fetch time on every
row. The older text-bulletin parser (pfz_scraper.py) stays for the bulletin
format; this is the one with a live source.

Each line carries Year and Julian_day, which date the advisory. INCOIS issues
PFZ advisories about three times a week, so a line older than MAX_AGE_DAYS is
treated as superseded rather than advice.

    PYTHONPATH=backend python -m dhruva.sources.pfz_wfs     # fetch and store
"""

from __future__ import annotations

import asyncio
import datetime as dt
import json
import os
import ssl
from dataclasses import dataclass
from typing import Any

import asyncpg
import httpx

GEOSERVER = "https://incois.gov.in/geoserver"
PORTAL = "https://incois.gov.in/geoportal/MFASPFZ/index.html"
USER_AGENT = "DHRUVA/0.1 (ISRO PS 26176 research prototype; contact via repository)"
MAX_AGE_DAYS = 3

LINES_URL = (
    f"{GEOSERVER}/PFZ_Automation/ows?service=WFS&version=1.1.0&request=GetFeature"
    "&typeName=PFZ_Automation:pfzlines&outputFormat=application/json"
)
CENTRES_URL = (
    f"{GEOSERVER}/PFZ_LandingCentres/ows?service=WFS&version=1.1.0&request=GetFeature"
    "&typeName=PFZ_LandingCentres:LandingCenters_29Apr2024&outputFormat=application/json"
)

CATEGORY_NAMES = {
    "chl": "chlorophyll",
    "sst": "sea surface temperature",
    "ghrsst": "sea surface temperature (GHRSST)",
}


@dataclass(frozen=True, slots=True)
class PfzLine:
    uid: str
    issued_for: dt.date
    category: str | None
    state_name: str | None
    serial: str | None
    geometry: dict[str, Any]


@dataclass(frozen=True, slots=True)
class LandingCentre:
    code: str
    name: str
    district: str | None
    sector: str | None
    lat: float
    lon: float


def julian_to_date(year: int, julian_day: int) -> dt.date:
    """INCOIS dates a line by day of year: day 1 is 1 January."""
    if not 1 <= julian_day <= 366:
        raise ValueError(f"julian day out of range: {julian_day}")
    return dt.date(year, 1, 1) + dt.timedelta(days=julian_day - 1)


def parse_lines(collection: dict[str, Any]) -> list[PfzLine]:
    """Feature collection to lines. A feature with no date or no geometry is
    dropped: an undated PFZ line cannot be told apart from last month's."""
    out: list[PfzLine] = []
    for feat in collection.get("features", []):
        p = feat.get("properties") or {}
        geom = feat.get("geometry")
        try:
            issued = julian_to_date(int(p["Year"]), int(p["Julian_day"]))
        except (KeyError, TypeError, ValueError):
            continue
        if not geom or geom.get("type") not in ("LineString", "MultiLineString"):
            continue
        if geom["type"] == "LineString":
            geom = {"type": "MultiLineString", "coordinates": [geom["coordinates"]]}
        uid = str(p.get("UID") or f"{p['Year']}{int(p['Julian_day']):03d}{p.get('Sno', '')}")
        out.append(
            PfzLine(
                uid=uid,
                issued_for=issued,
                category=p.get("Category"),
                state_name=(p.get("State_Name") or "").title() or None,
                serial=p.get("Sno"),
                geometry=geom,
            )
        )
    return out


def parse_centres(collection: dict[str, Any]) -> list[LandingCentre]:
    out: list[LandingCentre] = []
    for feat in collection.get("features", []):
        p = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates")
        if geom.get("type") != "Point" or not coords or not p.get("LC_NAME"):
            continue
        out.append(
            LandingCentre(
                code=str(p.get("LC_UNIQUE_") or p.get("OBJECTID")),
                name=str(p["LC_NAME"]).strip(),
                district=p.get("DIST_NAME"),
                sector=(p.get("SECTOR_NAM") or "").title() or None,
                lon=float(coords[0]),
                lat=float(coords[1]),
            )
        )
    return out


def _verify() -> ssl.SSLContext | bool:
    """INCOIS's servers omit an intermediate certificate (CLAUDE.md). Use the
    pinned bundle when configured; never turn verification off."""
    bundle = os.environ.get("INCOIS_CA_BUNDLE")
    if bundle and os.path.exists(bundle):
        return ssl.create_default_context(cafile=bundle)
    return True


async def fetch(client: httpx.AsyncClient, url: str) -> dict[str, Any]:
    r = await client.get(url)
    r.raise_for_status()
    return r.json()


async def store(
    conn: asyncpg.Connection,
    lines: list[PfzLine],
    centres: list[LandingCentre],
    fetched_at: dt.datetime,
) -> tuple[int, int]:
    for line in lines:
        await conn.execute(
            """
            INSERT INTO pfz_line
                (uid, issued_for, category, state_name, serial, source_url, fetched_at, geom)
            VALUES ($1,$2,$3,$4,$5,$6,$7, ST_SetSRID(ST_GeomFromGeoJSON($8), 4326))
            ON CONFLICT (uid) DO UPDATE
              SET geom = EXCLUDED.geom, fetched_at = EXCLUDED.fetched_at
            """,
            line.uid,
            line.issued_for,
            line.category,
            line.state_name,
            line.serial,
            PORTAL,
            fetched_at,
            json.dumps(line.geometry),
        )
    for c in centres:
        await conn.execute(
            """
            INSERT INTO landing_centre (code, name, district, sector, source_url, fetched_at, geom)
            VALUES ($1,$2,$3,$4,$5,$6, ST_SetSRID(ST_MakePoint($7,$8), 4326))
            ON CONFLICT (code) DO UPDATE
              SET name = EXCLUDED.name, geom = EXCLUDED.geom, fetched_at = EXCLUDED.fetched_at
            """,
            c.code,
            c.name,
            c.district,
            c.sector,
            PORTAL,
            fetched_at,
            c.lon,
            c.lat,
        )
    return len(lines), len(centres)


async def refresh(dsn: str) -> tuple[int, int, list[dt.date]]:
    """Fetch both layers and store them. Returns (lines, centres, advisory dates)."""
    from dhruva.geo.boundaries import apply_schema

    async with httpx.AsyncClient(
        timeout=90, headers={"User-Agent": USER_AGENT}, verify=_verify()
    ) as client:
        lines = parse_lines(await fetch(client, LINES_URL))
        centres = parse_centres(await fetch(client, CENTRES_URL))
    conn = await asyncpg.connect(dsn, timeout=10)
    try:
        await apply_schema(conn)
        n_lines, n_centres = await store(conn, lines, centres, dt.datetime.now(dt.UTC))
    finally:
        await conn.close()
    return n_lines, n_centres, sorted({line.issued_for for line in lines})


def main() -> None:
    from dhruva.config import database_dsn

    dsn = database_dsn()
    if not dsn:
        raise SystemExit("no database configured (DHRUVA_DSN or DATABASE_URL)")
    n_lines, n_centres, dates = asyncio.run(refresh(dsn))
    print(f"stored {n_lines} PFZ lines (advisories of {', '.join(map(str, dates))})")
    print(f"stored {n_centres} landing centres")
    print(f"source: {PORTAL}")


if __name__ == "__main__":
    main()
