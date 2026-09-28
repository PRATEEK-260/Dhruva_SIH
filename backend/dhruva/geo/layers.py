"""Whole-table GeoJSON for map display.

boundaries.py's nearest_boundaries/zones_containing are point-relative — "what
is closest to THIS lat/lon" — which is what the boat needs. Shore Console
needs everything in view at once, so these read the full tables instead.
Every boundary/zone feature carries indicative: true; every PFZ feature
carries source_url and fetched_at (CLAUDE.md).
"""

from __future__ import annotations

import json
from typing import Any

import asyncpg


async def all_boundaries_geojson(conn: asyncpg.Connection) -> dict[str, Any]:
    rows = await conn.fetch(
        "SELECT name, line_type, territory1, territory2, indicative, source_url, "
        "ST_AsGeoJSON(geom) AS geometry FROM boundary_line"
    )
    return _feature_collection(
        rows, ("name", "line_type", "territory1", "territory2", "indicative", "source_url")
    )


async def all_zones_geojson(conn: asyncpg.Connection) -> dict[str, Any]:
    rows = await conn.fetch(
        "SELECT name, zone_type, territory, sovereign, indicative, source_url, "
        "ST_AsGeoJSON(geom) AS geometry FROM maritime_zone"
    )
    return _feature_collection(
        rows, ("name", "zone_type", "territory", "sovereign", "indicative", "source_url")
    )


async def recent_pfz_geojson(conn: asyncpg.Connection) -> dict[str, Any]:
    """geom is nullable in the schema — a bulletin row can carry a bearing and
    distance without a resolved absolute point. Excluded here rather than
    crashing on ST_AsGeoJSON(NULL): a row with no geometry cannot be plotted
    on a map, which is this endpoint's entire purpose. It is still readable
    through the bulletin data directly, just not through this map layer."""
    rows = await conn.fetch(
        "SELECT region, landing_centre, bearing_deg, distance_nm, depth_m, "
        "source_url, source_name, fetched_at, ST_AsGeoJSON(geom) AS geometry "
        "FROM pfz_advisory WHERE geom IS NOT NULL "
        "AND (valid_until IS NULL OR valid_until > now()) "
        "ORDER BY issued_for DESC"
    )
    return _feature_collection(
        rows,
        (
            "region",
            "landing_centre",
            "bearing_deg",
            "distance_nm",
            "depth_m",
            "source_url",
            "source_name",
            "fetched_at",
        ),
    )


async def pfz_lines_geojson(conn: asyncpg.Connection) -> dict[str, Any]:
    """The latest INCOIS PFZ advisory's lines, if it is still fresh. One date
    only: lines from two advisories drawn together would show fish where the
    newer advisory no longer puts them."""
    from dhruva.sources.pfz_wfs import CATEGORY_NAMES, MAX_AGE_DAYS

    rows = await conn.fetch(
        """
        SELECT uid, issued_for, category, state_name, source_url, source_name, fetched_at,
               ST_AsGeoJSON(geom) AS geometry
        FROM pfz_line
        WHERE issued_for = (SELECT max(issued_for) FROM pfz_line)
          AND issued_for >= current_date - $1::int
        """,
        MAX_AGE_DAYS,
    )
    fc = _feature_collection(
        rows,
        ("uid", "issued_for", "category", "state_name", "source_url", "source_name", "fetched_at"),
    )
    for f in fc["features"]:
        cat = f["properties"]["category"] or ""
        f["properties"]["basis"] = CATEGORY_NAMES.get(cat, cat) if cat else None
    return fc


def _feature_collection(rows: list[asyncpg.Record], prop_keys: tuple[str, ...]) -> dict[str, Any]:
    features = []
    for row in rows:
        props: dict[str, Any] = {}
        for key in prop_keys:
            value = row[key]
            props[key] = value.isoformat() if hasattr(value, "isoformat") else value
        features.append(
            {"type": "Feature", "geometry": json.loads(row["geometry"]), "properties": props}
        )
    return {"type": "FeatureCollection", "features": features}
