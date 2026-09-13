"""The advisory request log.

This is NOT vessel tracking. No boat in this architecture ever reports a
position back to shore (CLAUDE.md: the NavIC uplink is ISRO's, no team
transmits) — this table only records that an advisory was requested, from
where, and what verdict came back. Shore Console's fleet list reads this as a
proxy for "who has been asking recently," never as "where boats currently
are."
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import asyncpg

SCHEMA_SQL = Path(__file__).with_name("schema.sql")


async def apply_schema(conn: asyncpg.Connection) -> None:
    await conn.execute(SCHEMA_SQL.read_text(encoding="utf-8"))


async def insert_advisory(
    conn: asyncpg.Connection, *, boat_class: str, lat: float, lon: float, risk_class: str
) -> None:
    await conn.execute(
        "INSERT INTO advisory_log (boat_class, lat, lon, risk_class) VALUES ($1, $2, $3, $4)",
        boat_class,
        lat,
        lon,
        risk_class,
    )


async def recent_advisories(conn: asyncpg.Connection, *, limit: int = 20) -> list[dict[str, Any]]:
    rows = await conn.fetch(
        "SELECT id, boat_class, lat, lon, risk_class, issued_at "
        "FROM advisory_log ORDER BY issued_at DESC LIMIT $1",
        limit,
    )
    return [dict(r) for r in rows]
