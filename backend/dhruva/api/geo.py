"""Boundary/zone/PFZ layers for the map, as plain GeoJSON.

No tile server exists yet (no TiTiler, no pg_tileserv) — these tables are
small enough (hundreds of rows) to ship whole over REST rather than tiled.
SST/chlorophyll/wave height are gridded rasters and need the tile pipeline
regardless; they are not part of this router.
"""

from __future__ import annotations

import os
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException

from dhruva.geo.layers import all_boundaries_geojson, all_zones_geojson, recent_pfz_geojson

router = APIRouter(prefix="/geo", tags=["geo"])


async def _connect() -> asyncpg.Connection:
    dsn = os.environ.get("DHRUVA_DSN")
    if not dsn:
        raise HTTPException(503, "DHRUVA_DSN not configured")
    try:
        return await asyncpg.connect(dsn, timeout=5)
    except OSError as exc:
        raise HTTPException(503, "database not reachable") from exc


@router.get("/boundaries")
async def get_boundaries() -> dict[str, Any]:
    conn = await _connect()
    try:
        return await all_boundaries_geojson(conn)
    finally:
        await conn.close()


@router.get("/zones")
async def get_zones() -> dict[str, Any]:
    conn = await _connect()
    try:
        return await all_zones_geojson(conn)
    finally:
        await conn.close()


@router.get("/pfz")
async def get_pfz() -> dict[str, Any]:
    conn = await _connect()
    try:
        return await recent_pfz_geojson(conn)
    finally:
        await conn.close()
