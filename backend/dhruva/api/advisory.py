"""The one HTTP door onto the graph. Everything here is a thin wrapper: state
building and graph invocation are dhruva.graph.build.arun's job already."""

from __future__ import annotations

import datetime as dt
from typing import Any

import asyncpg
from fastapi import APIRouter
from pydantic import BaseModel

from dhruva.api.store import apply_schema, insert_advisory, recent_advisories
from dhruva.config import database_dsn
from dhruva.graph.build import arun
from dhruva.graph.state import BoatClass

router = APIRouter(tags=["advisory"])

# Not imported from dhruva.app: app.py registers this router, so importing
# ADVISORY_NOTICE from there would be circular. The graph's own evidence
# bundle already carries this exact string as EvidenceBundle.notice's default
# (evidence/schema.py) and render_template's fallback path always populates
# it, so state["evidence"]["notice"] is the more correct source anyway — it is
# what the graph actually said, not a constant redeclared a fourth time.
_FALLBACK_NOTICE = "Advisory only. Follow official INCOIS and IMD warnings."


class AdvisoryRequest(BaseModel):
    query: str
    lat: float
    lon: float
    language: str = "en"
    boat_class: BoatClass = BoatClass.FRP_UNDER_12M
    when: dt.datetime | None = None


class AdvisoryResponse(BaseModel):
    narration: str
    risk_class: str
    firewall_passed: bool
    evidence: dict[str, Any]
    capsule_base32: str
    reason_code: int
    notice: str


async def _connect() -> asyncpg.Connection | None:
    """Best-effort only: a request-log write failing (no DB configured) must
    never block an advisory a crew is waiting on."""
    dsn = database_dsn()
    if not dsn:
        return None
    try:
        return await asyncpg.connect(dsn, timeout=5)
    except OSError:
        return None


@router.post("/advisory", response_model=AdvisoryResponse)
async def post_advisory(req: AdvisoryRequest) -> AdvisoryResponse:
    state = await arun(
        req.query,
        req.lat,
        req.lon,
        language=req.language,
        boat_class=req.boat_class,
        when=req.when,
    )
    risk_class = state.get("risk_class")
    risk_class_value = risk_class.value if risk_class is not None else "unknown"

    conn = await _connect()
    if conn is not None:
        try:
            await apply_schema(conn)
            await insert_advisory(
                conn,
                boat_class=req.boat_class.value,
                lat=req.lat,
                lon=req.lon,
                risk_class=risk_class_value,
            )
        finally:
            await conn.close()

    evidence = state.get("evidence", {})
    return AdvisoryResponse(
        narration=state.get("narration", ""),
        risk_class=risk_class_value,
        firewall_passed=state.get("firewall_passed", False),
        evidence=evidence,
        capsule_base32=state.get("capsule_bits", ""),
        reason_code=state.get("reason_code", 0),
        notice=evidence.get("notice") or _FALLBACK_NOTICE,
    )


@router.get("/advisory/recent")
async def get_recent_advisories(limit: int = 20) -> list[dict[str, Any]]:
    limit = min(max(limit, 1), 100)
    conn = await _connect()
    if conn is None:
        return []
    try:
        await apply_schema(conn)
        rows = await recent_advisories(conn, limit=limit)
    finally:
        await conn.close()
    return [{**row, "issued_at": row["issued_at"].isoformat()} for row in rows]
