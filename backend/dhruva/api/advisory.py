"""The one HTTP door onto the graph. Everything here is a thin wrapper: state
building and graph invocation are dhruva.graph.build.arun's job already."""

from __future__ import annotations

import datetime as dt
from typing import Any

import asyncpg
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from dhruva.api.store import apply_schema, insert_advisory, recent_advisories
from dhruva.api.trace import build_trace, visualization
from dhruva.config import database_dsn
from dhruva.demo import replay
from dhruva.graph.build import arun
from dhruva.graph.state import BoatClass, DhruvaState
from dhruva.sources.imd_bulletin import (
    BulletinError,
    cyclone_source,
    live_status,
    overall_status,
)

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
    # Shore inspecting a point is not a boat asking; logging it would put a
    # vessel on the request list that never existed.
    log: bool = True
    # TEST INPUT: a hand-placed cyclone, for the shore console's drill. Live IMD
    # bulletins (sources/imd_feed.py) apply on their own; this overrides only
    # their distance, and the evidence row says it is a test input.
    test_cyclone_km: float | None = None
    # TEST INPUT. Alert types as a warning feed would name them; an unrecognised
    # one forces at least CAUTION (default-deny).
    test_alerts: list[str] = []
    # A stored past IMD bulletin (data/imd/bulletins.json). The cyclone distance is
    # then worked out from the centre IMD published, not supplied as a test input.
    bulletin: str | None = None


class AdvisoryResponse(BaseModel):
    narration: str
    risk_class: str
    firewall_passed: bool
    evidence: dict[str, Any]
    capsule_base32: str
    reason_code: int
    notice: str
    intent: str = "conditions"
    fired_rules: list[str] = []
    hazard_flags: list[str] = []
    # The problem statement's nine agents: ran or skipped, one line each.
    trace: list[dict[str, Any]] = []
    view: dict[str, list[str]] = {}
    boundaries: list[dict[str, Any]] = []
    # Nearest line of the latest fresh INCOIS PFZ advisory, or null.
    pfz: dict[str, Any] | None = None
    # Query #7's answer: status, the rendered parts and each variable's change.
    # Online only; the capsule cannot carry a baseline. Null for other questions.
    decline: dict[str, Any] | None = None
    # The spoken answer for the brief's other example queries (answers/):
    # kind ("avoid", "thunder", "tide", "productive", "route"), status, lines.
    answer: dict[str, Any] | None = None
    # Set only when this is a recorded run replayed (dhruva/demo/replay.py):
    # when it was recorded, and why it was used instead of a live run.
    recorded_at: str | None = None
    replay_reason: str | None = None
    # What IMD's live bulletins say for this boat: status ("active", "none",
    # "unchecked"), a line for the screen, and each bulletin in force with its
    # link and fishermen warning. Null for a replayed past storm.
    imd: dict[str, Any] | None = None


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
    cyclone = None
    imd: dict[str, Any] | None = None
    alerts = list(req.test_alerts)
    if req.bulletin is not None:
        try:
            cyclone = cyclone_source(req.bulletin, req.lat, req.lon, req.when)
        except BulletinError as exc:
            raise HTTPException(422, str(exc)) from exc
    else:
        live = live_status(req.lat, req.lon, req.when)
        if live["status"] != "not_applicable":
            imd = {k: v for k, v in live.items() if k not in ("cyclone", "alerts")}
            alerts += live["alerts"]
            if req.test_cyclone_km is None:
                cyclone = live["cyclone"]
    rec_key = replay.key(
        req.query,
        req.language,
        req.lat,
        req.lon,
        req.boat_class.value,
        req.when,
        req.test_cyclone_km,
        req.test_alerts,
        req.bulletin,
    )
    mode = replay.mode()
    recorded = replay.find(rec_key) if mode != "off" else None

    if mode == "replay" and recorded is not None:
        response = AdvisoryResponse(**{**recorded, "replay_reason": "demo mode"})
    else:
        try:
            state = await arun(
                req.query,
                req.lat,
                req.lon,
                language=req.language,
                boat_class=req.boat_class,
                when=req.when,
                cyclone_distance_km=(
                    cyclone["distance_km"] if cyclone is not None else req.test_cyclone_km
                ),
                cyclone_source=cyclone,
                alerts=alerts,
                imd=imd,
            )
        except Exception as exc:
            if recorded is None:
                raise HTTPException(502, f"advisory failed: {type(exc).__name__}") from exc
            state = None
        if state is None or (recorded is not None and replay.live_failed(dict(state))):
            assert recorded is not None
            response = AdvisoryResponse(**{**recorded, "replay_reason": "live sources failed"})
        else:
            response = _from_state(state)
            response.imd = imd

    conn = await _connect() if req.log else None
    if conn is not None:
        try:
            await apply_schema(conn)
            await insert_advisory(
                conn,
                boat_class=req.boat_class.value,
                lat=req.lat,
                lon=req.lon,
                risk_class=response.risk_class,
                valid_for=req.when,
            )
        finally:
            await conn.close()
    return response


def _from_state(state: DhruvaState) -> AdvisoryResponse:
    risk_class = state.get("risk_class")
    evidence = state.get("evidence", {})
    intent = state.get("intent")
    return AdvisoryResponse(
        narration=state.get("narration", ""),
        risk_class=risk_class.value if risk_class is not None else "unknown",
        firewall_passed=state.get("firewall_passed", False),
        evidence=evidence,
        capsule_base32=state.get("capsule_bits", ""),
        reason_code=state.get("reason_code", 0),
        notice=evidence.get("notice") or _FALLBACK_NOTICE,
        intent=intent.value if intent is not None else "conditions",
        fired_rules=list(state.get("fired_rules", [])),
        hazard_flags=list(state.get("hazard_flags", [])),
        trace=build_trace(state),
        view=visualization(intent),
        boundaries=list(state.get("boundaries", [])),
        pfz=state.get("pfz"),
        decline=state.get("decline_answer"),
        answer=state.get("answer"),
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
    return [
        {
            **row,
            "issued_at": row["issued_at"].isoformat(),
            "valid_for": row["valid_for"].isoformat() if row["valid_for"] else None,
        }
        for row in rows
    ]


@router.get("/imd/status")
async def get_imd_status() -> dict[str, Any]:
    """IMD National Bulletins in force, from the last check of IMD's archive
    (sources/imd_feed.py). Read and attributed; IMD offers no feed."""
    return overall_status()
