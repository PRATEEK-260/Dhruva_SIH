"""advisory_log is a request log, never vessel tracking. These tests exist to
hold that distinction, not just the CRUD."""

import os

import asyncpg
import pytest

from dhruva.api.store import apply_schema, insert_advisory, recent_advisories

pytestmark = pytest.mark.asyncio


async def _conn():
    dsn = os.environ.get("DHRUVA_DSN")
    if not dsn:
        pytest.skip("DHRUVA_DSN not set")
    try:
        return await asyncpg.connect(dsn, timeout=5)
    except OSError:
        pytest.skip("database not reachable")


async def test_insert_then_read_back():
    conn = await _conn()
    try:
        await apply_schema(conn)
        await conn.execute("DELETE FROM advisory_log")
        await insert_advisory(
            conn, boat_class="frp_under_12m", lat=11.05, lon=79.95, risk_class="caution"
        )
        rows = await recent_advisories(conn, limit=10)
        assert len(rows) == 1
        assert rows[0]["boat_class"] == "frp_under_12m"
        assert rows[0]["risk_class"] == "caution"
        assert rows[0]["lat"] == pytest.approx(11.05)
    finally:
        await conn.close()


async def test_recent_advisories_orders_newest_first():
    conn = await _conn()
    try:
        await apply_schema(conn)
        await conn.execute("DELETE FROM advisory_log")
        for risk in ("safe", "caution", "no_go"):
            await insert_advisory(
                conn, boat_class="frp_under_12m", lat=11.0, lon=80.0, risk_class=risk
            )
        rows = await recent_advisories(conn, limit=10)
        assert [r["risk_class"] for r in rows] == ["no_go", "caution", "safe"]
    finally:
        await conn.close()


async def test_limit_caps_the_result_set():
    conn = await _conn()
    try:
        await apply_schema(conn)
        await conn.execute("DELETE FROM advisory_log")
        for _ in range(5):
            await insert_advisory(
                conn, boat_class="frp_under_12m", lat=11.0, lon=80.0, risk_class="safe"
            )
        rows = await recent_advisories(conn, limit=2)
        assert len(rows) == 2
    finally:
        await conn.close()
