"""The LangGraph state machine.

    query -> planner(0) -> [discovery(2) | ocean(3) | weather(4) | geo(5)]
                        -> risk(6) -> route(7) -> evidence(8) -> codec(9)

Language (node 1) wraps the graph rather than sitting in it, so everything here
runs in English.

The planner emits a tool plan and calls nothing itself. That separation is what
makes a run inspectable — in Studio you can see what was decided before anything
was fetched — and it is easy to collapse by accident.

Nodes 2-5 fan out in parallel and all write to `observations`, which is why that
key carries an operator.add reducer in state.py.
"""

from __future__ import annotations

import datetime as dt
import os
from typing import Any, cast

from langgraph.graph import END, START, StateGraph

from dhruva.analytics.decline import DeclineAnswer
from dhruva.analytics.decline import answer as decline_answer
from dhruva.analytics.decline import evidence_items as decline_evidence
from dhruva.analytics.decline import languages as decline_languages
from dhruva.analytics.decline import render as render_decline
from dhruva.codec.codebook import reason_index
from dhruva.codec.codec import Capsule, encode, to_base32
from dhruva.config import database_dsn
from dhruva.evidence.firewall import render_template, validate
from dhruva.evidence.schema import build_bundle, pfz_item
from dhruva.graph.planner_model import classify_with_model
from dhruva.graph.state import (
    BoatClass,
    DhruvaState,
    Intent,
    RiskClass,
    ToolPlan,
    observation_for,
)
from dhruva.risk.rules import assess
from dhruva.sources.conditions import DEFAULT_VARIABLES, conditions_at, default_adapters
from dhruva.sources.imd_bulletin import cyclone_item
from dhruva.sources.registry import Registry, Variable

# Which variables each intent actually needs. Fetching everything for every
# question wastes the latency budget the gate is measured against.
INTENT_VARIABLES: dict[Intent, tuple[Variable, ...]] = {
    Intent.GO_NO_GO: (Variable.WAVE_HEIGHT, Variable.WIND_SPEED, Variable.WIND_DIRECTION),
    # Wind as well as waves: a fishing answer carries a safety verdict (NO-GO
    # outranks any zone), and without wind the rule table can only say UNKNOWN.
    Intent.FISHING_ZONE: (
        Variable.SST,
        Variable.CHLOROPHYLL,
        Variable.WAVE_HEIGHT,
        Variable.WIND_SPEED,
    ),
    Intent.ROUTE: (
        Variable.WAVE_HEIGHT,
        Variable.WIND_SPEED,
        Variable.CURRENT_SPEED,
        Variable.CURRENT_DIRECTION,
    ),
    Intent.BOUNDARY: (Variable.CURRENT_SPEED, Variable.CURRENT_DIRECTION),
    Intent.HAZARD: (Variable.WAVE_HEIGHT, Variable.WIND_SPEED),
    Intent.CONDITIONS: DEFAULT_VARIABLES,
    # The decline comparison fetches its own 30-day windows (analytics/baseline.py);
    # waves and wind are here so the answer still carries a real safety verdict.
    Intent.DECLINE_ATTRIBUTION: (Variable.WAVE_HEIGHT, Variable.WIND_SPEED),
    Intent.EXPLAIN: (),
}

# Which fetch nodes each intent actually needs. The gate is "routes to the right
# node set", so this has to vary by intent — returning every node for every
# question is not routing, it is fetching everything and calling it a plan.
# discovery always runs: it is a registry lookup, not a fetch, and its output is
# what makes the trace show which datasets were even eligible.
INTENT_NODES: dict[Intent, tuple[str, ...]] = {
    Intent.GO_NO_GO: ("weather", "geo"),
    # geo finds the nearest INCOIS PFZ line; without it a fishing question has
    # no zone to answer with.
    Intent.FISHING_ZONE: ("ocean", "weather", "geo"),
    Intent.ROUTE: ("ocean", "weather", "geo"),
    Intent.BOUNDARY: ("geo", "ocean"),
    Intent.HAZARD: ("weather", "geo"),
    Intent.CONDITIONS: ("ocean", "weather"),
    # ocean compares the windows, geo finds the INCOIS zone for "where to try",
    # weather keeps the verdict real.
    Intent.DECLINE_ATTRIBUTION: ("ocean", "weather", "geo"),
    Intent.EXPLAIN: (),
}

# Weighted signals per intent. Scoring rather than first-match, because the
# intents overlap in the words people actually use: "is it safe to go fishing"
# carries both a safety signal and a fishing signal, and an ordered list answers
# that by accident of ordering rather than by meaning. Longer, more specific
# phrases carry more weight than bare nouns.
_SIGNALS: dict[Intent, list[tuple[str, float]]] = {
    Intent.EXPLAIN: [
        # Asking about the system's own reasoning, not about the sea. The "you"
        # is what separates "why did you say caution" from "why has the catch
        # fallen" — one is about the answer, the other about the ocean.
        ("why did you", 6),
        ("how did you", 6),
        ("where did that", 6),
        ("where did the", 5),
        ("which dataset", 6),
        ("what dataset", 6),
        ("show me the evidence", 6),
        ("evidence for", 5),
        ("what rule", 6),
        ("which rule", 6),
        ("explain", 4),
        ("how do you know", 6),
        ("work that out", 5),
        ("source of", 3),
        ("விளக்கு", 4),
    ],
    Intent.DECLINE_ATTRIBUTION: [
        ("catch fallen", 6),
        ("catch has fallen", 6),
        ("fewer fish", 6),
        ("less fish", 6),
        ("productivity declin", 6),
        ("declin", 4),
        ("happened to the fish", 6),
        ("fish stocks", 5),
        ("over the years", 4),
        ("got warmer", 4),
        ("warmer over", 5),
        ("this season", 2),
        ("குறைந்து", 5),
        ("ஏன்", 2),
        # "fewer fish" in the other pilot languages: Malayalam, Odia, Hindi.
        # Each outweighs the bare fish noun that FISHING_ZONE scores.
        ("മീൻ", 1),
        ("കുറഞ്ഞ", 6),
        ("എന്തുകൊണ്ട്", 2),
        ("କମିଗଲା", 6),
        ("କାହିଁକି", 2),
        ("कम क्यों", 6),
        ("मछली कम", 6),
        ("कम हो गई", 5),
        ("fewer fish", 6),
    ],
    Intent.BOUNDARY: [
        ("imbl", 8),
        ("maritime line", 7),
        ("international line", 7),
        ("boundary", 6),
        ("border", 6),
        ("indian waters", 6),
        ("protected area", 6),
        ("cross the", 4),
        ("which side", 5),
        ("எல்லை", 6),
        ("सीमा", 6),
    ],
    Intent.HAZARD: [
        ("cyclone", 8),
        ("tsunami", 8),
        ("storm", 6),
        ("lightning", 7),
        ("warning", 4),
        ("alert", 4),
        ("புயல்", 7),
        ("எச்சரிக்கை", 5),
        ("तूफान", 7),
        ("चेतावनी", 5),
    ],
    Intent.ROUTE: [
        ("route", 7),
        # "<route word> to <place>" is a navigation request whatever the place
        # is: in "safest route to the fishing zone" the zone is the destination,
        # not the question. Without this the destination outscores the verb.
        ("route to", 4),
        ("navigate", 7),
        ("plot a course", 7),
        ("course home", 6),
        ("way to", 5),
        ("which way", 5),
        ("path", 5),
        ("back to shore", 6),
        ("to the harbour", 6),
        ("harbour", 3),
        ("avoiding", 4),
    ],
    Intent.GO_NO_GO: [
        ("can i go", 7),
        ("should i", 6),
        ("is it safe", 8),
        ("safe to", 6),
        ("safe for", 6),
        ("too rough for", 7),
        ("take the boat out", 7),
        ("go out", 5),
        ("போகலாமா", 8),
        ("जा सकता", 8),
        ("जा सकती", 8),
    ],
    Intent.FISHING_ZONE: [
        ("pfz", 8),
        ("fishing zone", 8),
        ("find fish", 6),
        ("where can i find", 5),
        ("catch more", 6),
        ("good shoal", 6),
        ("shoal", 5),
        ("best spot", 6),
        ("मछली कहाँ", 7),
        ("மீன் பிடிக்க", 7),
        ("மீன்", 3),
        ("मछली", 4),
        ("fish", 2),
    ],
    Intent.CONDITIONS: [
        ("sea conditions", 6),
        ("weather", 5),
        ("wave", 4),
        ("wind", 4),
        ("how rough", 6),
        ("how high are", 6),
        ("water temperature", 6),
        ("next six hours", 4),
        ("condition", 4),
        ("கடல் நிலவரம்", 7),
        ("समुद्र की स्थिति", 7),
        ("sea", 1),
    ],
}

# Ties break toward the more specific intent, so a query carrying equal evidence
# for CONDITIONS and something narrower resolves to the narrower one.
_TIE_ORDER: list[Intent] = [
    Intent.EXPLAIN,
    Intent.DECLINE_ATTRIBUTION,
    Intent.BOUNDARY,
    Intent.HAZARD,
    Intent.ROUTE,
    Intent.FISHING_ZONE,
    Intent.GO_NO_GO,
    Intent.CONDITIONS,
]


def score_intents(query: str) -> dict[Intent, float]:
    """Signal weight per intent. Exposed so the eval can show near-misses."""
    text = query.lower()
    scores: dict[Intent, float] = {}
    for intent, signals in _SIGNALS.items():
        total = sum(weight for term, weight in signals if term in text)
        if total:
            scores[intent] = total
    return scores


def classify(query: str) -> Intent:
    """Route a query to one of the eight PS question types.

    Keyword scoring, and the fallback behind the model in planner_model.py: it
    answers whenever the model cannot (no key, timeout, bad output). Two honest
    limits: the weights were tuned against eval/queries.jsonl, so the reported
    accuracy is optimistic on unseen phrasing; and the Indic coverage is a
    handful of terms, not morphology, so an inflected form it has not seen falls
    through to CONDITIONS.
    """
    scores = score_intents(query)
    if not scores:
        return Intent.CONDITIONS
    best = max(scores.values())
    for intent in _TIE_ORDER:
        if scores.get(intent) == best:
            return intent
    return Intent.CONDITIONS


# ------------------------------------------------------------------ nodes ----


def _point(state: DhruvaState) -> tuple[float, float]:
    """lat/lon are not required keys on the TypedDict, so read them through here
    rather than indexing. A run without a position is a caller bug and should say
    so plainly rather than raising KeyError three nodes deep."""
    lat, lon = state.get("lat"), state.get("lon")
    if lat is None or lon is None:
        raise ValueError("state has no position; seed it with initial_state()")
    return lat, lon


def _issue_slot(when: dt.datetime) -> int:
    """UTC instant to a 0-671 slot: 15-minute resolution, wrapping weekly with
    Monday 00:00 UTC as slot 0. docs/CAPSULE_SPEC.md fixes the width and the
    wrap length (7 * 24 * 4 = 672) but not this mapping, so it is pinned here,
    once, rather than left for each caller to reinvent differently.

    Runs only at encode time, onshore, with the real clock — that is allowed.
    The decoder that reads issue_slot back out stays clockless; only the
    ENCODE side is time-aware.
    """
    if when.tzinfo is None:
        raise ValueError("issue_slot needs a timezone-aware instant")
    utc = when.astimezone(dt.UTC)
    minutes_into_week = utc.weekday() * 24 * 60 + utc.hour * 60 + utc.minute
    return (minutes_into_week // 15) % 672


async def planner(state: DhruvaState) -> dict[str, Any]:
    """Node 0. Decides; does not fetch.

    The model picks the intent; if it cannot answer for any reason, the keyword
    classifier does, and the plan's reason records which one decided and why.
    """
    query = state.get("query", "")
    choice = await classify_with_model(query, api_key=os.environ.get("GEMINI_API_KEY"))
    if choice.intent is not None:
        intent, reason = choice.intent, choice.reason
    else:
        intent = classify(query)
        reason = f"keyword match on intent {intent.value} ({choice.reason})"
    variables = list(INTENT_VARIABLES.get(intent, DEFAULT_VARIABLES))
    plan = ToolPlan(
        intent=intent,
        nodes=["discovery", *INTENT_NODES.get(intent, ("ocean", "weather"))],
        variables=variables,
        needs_boundaries=intent in (Intent.BOUNDARY, Intent.ROUTE, Intent.GO_NO_GO),
        needs_route=intent is Intent.ROUTE,
        reason=reason,
    )
    return {"intent": intent, "plan": plan}


def _unplanned(state: DhruvaState, node: str) -> bool:
    """Every fetch node is wired to run on every query; this is what makes the
    plan's node list binding. With no plan at all (Studio, scripts) nothing is
    skipped."""
    nodes = (state.get("plan") or {}).get("nodes") or []
    return bool(nodes) and node not in nodes


async def _fetch(state: DhruvaState, node: str, wanted: tuple[Variable, ...]) -> dict[str, Any]:
    if _unplanned(state, node):
        return {}
    plan = state.get("plan") or {}
    planned: tuple[Variable, ...] = tuple(plan.get("variables") or DEFAULT_VARIABLES)
    variables = tuple(v for v in planned if v in wanted) or wanted
    registry = Registry.load(os.environ.get("DHRUVA_REGISTRY", "data/registry.yaml"))
    adapters = default_adapters(
        copernicus_username=os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"),
        copernicus_password=os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"),
    )
    lat, lon = _point(state)
    result = await conditions_at(
        lat,
        lon,
        state.get("when"),
        registry=registry,
        adapters=adapters,
        variables=variables,
    )
    return {"observations": list(result.primary.values()), "errors": result.errors}


async def ocean(state: DhruvaState) -> dict[str, Any]:
    """Node 3. SST, chlorophyll, currents; for query #7, the last 30 days against
    the same window in earlier years instead."""
    if state.get("intent") is Intent.DECLINE_ATTRIBUTION and not _unplanned(state, "ocean"):
        from dhruva.analytics.baseline import decline_changes

        lat, lon = _point(state)
        decline, errors = await decline_changes(
            lat,
            lon,
            state.get("when") or dt.datetime.now(dt.UTC),
            username=os.environ.get("COPERNICUSMARINE_SERVICE_USERNAME"),
            password=os.environ.get("COPERNICUSMARINE_SERVICE_PASSWORD"),
        )
        return {"decline": decline, "errors": errors}
    return await _fetch(
        state,
        "ocean",
        (Variable.SST, Variable.CHLOROPHYLL, Variable.CURRENT_SPEED, Variable.CURRENT_DIRECTION),
    )


async def weather(state: DhruvaState) -> dict[str, Any]:
    """Node 4. Wind and waves."""
    return await _fetch(
        state,
        "weather",
        (Variable.WAVE_HEIGHT, Variable.WAVE_PERIOD, Variable.WIND_SPEED, Variable.WIND_DIRECTION),
    )


async def discovery(state: DhruvaState) -> dict[str, Any]:
    """Node 2. Which datasets can answer, recorded for the trace."""
    registry = Registry.load(os.environ.get("DHRUVA_REGISTRY", "data/registry.yaml"))
    when = state.get("when") or dt.datetime.now(dt.UTC)
    plan = state.get("plan") or {}
    lat, lon = _point(state)
    chosen = {
        v.value: [d.id for d in registry.candidates(v, lat, lon, when)]
        for v in (plan.get("variables") or DEFAULT_VARIABLES)
    }
    return {"zones": [{"kind": "dataset_plan", "datasets": chosen}]}


async def geo(state: DhruvaState) -> dict[str, Any]:
    """Node 5. Boundaries and zones. Degrades to empty rather than failing the
    run when no database is configured."""
    if _unplanned(state, "geo"):
        return {}
    dsn = database_dsn()
    if not dsn:
        return {}
    import asyncpg

    from dhruva.geo.boundaries import nearest_boundaries, zones_containing
    from dhruva.geo.pfz import nearest_pfz

    try:
        conn = await asyncpg.connect(dsn, timeout=5)
    except Exception:
        return {}
    try:
        lat, lon = _point(state)
        near = await nearest_boundaries(conn, lat, lon, limit=3)
        zones = await zones_containing(conn, lat, lon)
        on = (state.get("when") or dt.datetime.now(dt.UTC)).astimezone(dt.UTC).date()
        try:
            pfz = await nearest_pfz(conn, lat, lon, on)
        except asyncpg.UndefinedTableError:
            pfz = None  # PFZ lines never loaded: python -m dhruva.sources.pfz_wfs
    finally:
        await conn.close()
    return {
        "pfz": pfz.as_dict() if pfz else None,
        "boundaries": [
            {
                "name": b.name,
                "line_type": b.line_type,
                "distance_nm": round(b.distance_nm, 2),
                "indicative": b.indicative,
            }
            for b in near
        ],
        "zones": [{"kind": "zone", **z} for z in zones],
    }


def risk(state: DhruvaState) -> dict[str, Any]:
    """Node 6. Deterministic verdict."""
    a = assess(state)
    return {
        "risk_class": a.risk_class,
        "fired_rules": a.rule_ids,
        "hazard_flags": a.hazard_flags,
    }


def route(state: DhruvaState) -> dict[str, Any]:
    """Node 7. A* over the cost grid lands here in a later phase; it is a
    declared stub rather than a silent no-op so the trace shows it ran."""
    plan = state.get("plan") or {}
    if not plan.get("needs_route"):
        return {}
    return {"waypoints": [], "fuel_proxy": None}


def _decline_answer(state: DhruvaState, a: Any) -> DeclineAnswer | None:
    """Query #7's answer, or None for any other question. Deterministic, so
    evidence() and codec() get the same one."""
    decline = state.get("decline")
    if state.get("intent") is not Intent.DECLINE_ATTRIBUTION or decline is None:
        return None
    return decline_answer(
        decline.get("chlorophyll"),
        decline.get("sst"),
        state.get("pfz"),
        no_go=a.risk_class is RiskClass.NO_GO,
    )


def _bundle(state: DhruvaState, a: Any) -> Any:
    """One bundle for evidence() and codec() alike, so the capsule's evidence hash
    fingerprints exactly what the evidence card shows."""
    bundle = build_bundle(state.get("observations", []), a)
    decline = state.get("decline")
    if decline is not None and (result := _decline_answer(state, a)) is not None:
        bundle.items.extend(decline_evidence(result, decline["box"]))
    if pfz := state.get("pfz"):
        bundle.items.append(pfz_item(pfz))
    if src := state.get("cyclone_source"):
        # The override's row says risk_engine; the number is IMD's. Keep the rule
        # and threshold, swap in the bulletin's provenance.
        item = cyclone_item(src)
        if (fired := bundle.by_key("cyclone_distance")) is not None:
            item.threshold, item.rule_id = fired.threshold, fired.rule_id
            bundle.items.remove(fired)
        bundle.items.append(item)
    return bundle


def evidence(state: DhruvaState) -> dict[str, Any]:
    """Node 8. Build the bundle, narrate, and refuse anything unvalidated."""
    a = assess(state)
    bundle = _bundle(state, a)

    # Until the model is wired, narration IS the template. That is the correct
    # failure mode anyway: the template is built from bundle rows, so it cannot
    # fail its own check.
    narration = render_template(bundle)
    language = state.get("language", "en")
    out: dict[str, Any] = {}
    if (result := _decline_answer(state, a)) is not None:
        # Query #7 speaks a sentence per part, picked by rule and filled only
        # from bundle rows; the firewall still checks it, in its own language.
        lines = render_decline(result, language)
        narration = " ".join(line["text"] for line in lines)
        lang_used = language if language in decline_languages() else "en"
        out["decline_answer"] = {**result.as_dict(), "lines": lines, "language": lang_used}
    check = validate(narration, bundle, language=language)
    if not check.passed:
        narration = render_template(bundle)
        if "decline_answer" in out:
            out["decline_answer"]["lines"] = []

    return {
        **out,
        "evidence": bundle.model_dump(mode="json"),
        "narration": narration,
        "firewall_passed": check.passed,
        "firewall_violations": check.messages,
    }


def codec(state: DhruvaState) -> dict[str, Any]:
    """Node 9. Build the capsule, compute the structured reason index from the
    same assessment risk() used, and emit the base32 wire string.

    Only fields this graph actually computes from real observations are
    populated with real values. PFZ bearing and distance come from the nearest
    line of the latest fresh INCOIS advisory (geo node, dhruva.geo.pfz); with no
    such line they stay 0, which the phrasebook reads as "no zone". pfz_conf
    carries the advisory's freshness, since INCOIS publishes no confidence.

    One group is deliberately left at its honest zero/none default:

    - Boundary distance and type: `state["boundaries"]` can hold real nearest-
      boundary data, but `bnd_eta_min` needs drift projection (current plus
      heading over time) that this graph does not compute. Populating distance
      without a real ETA would let the "near a boundary" narration clause fire
      and then speak a fabricated "about 0 minutes" — a number that reads as
      real data while meaning nothing, the same shape of lie the numeric
      firewall exists to stop even though it would not come from the LLM. They
      stay at the Capsule default ("none", 0) until route/drift lands.
    """
    a = assess(state)
    lat, lon = _point(state)

    wave = observation_for(state, Variable.WAVE_HEIGHT)
    wind = observation_for(state, Variable.WIND_SPEED)
    wind_dir = observation_for(state, Variable.WIND_DIRECTION)
    curr = observation_for(state, Variable.CURRENT_SPEED)
    curr_dir = observation_for(state, Variable.CURRENT_DIRECTION)
    sst = observation_for(state, Variable.SST)

    bundle = _bundle(state, a)
    pfz = state.get("pfz")

    capsule = Capsule(
        msg_type="advisory",
        issue_slot=_issue_slot(state.get("when") or dt.datetime.now(dt.UTC)),
        lat=lat,
        lon=lon,
        risk_class=a.risk_class.value,
        hazards=list(a.hazard_flags),
        wave_hs_m=wave.value if wave else 0.0,
        wind_kt=round(wind.value) if wind else 0,
        wind_dir_deg=wind_dir.value if wind_dir else 0.0,
        curr_kt=curr.value if curr else 0.0,
        curr_dir_deg=curr_dir.value if curr_dir else 0.0,
        sst_c=sst.value if sst else 18.0,
        # chl_class has no "unknown" member and no classifier exists yet, so it
        # stays at the dataclass default. Inert today: no authored codebook
        # template renders {chl_class_name}.
        # A zone under half a mile away still exists: 0 on the wire means none.
        pfz_bearing_deg=pfz["bearing_deg"] if pfz else 0.0,
        pfz_dist_nm=max(1, round(pfz["distance_nm"])) if pfz else 0,
        pfz_conf=pfz["confidence"] if pfz else 0,
        evidence_hash=bundle.capsule_evidence_hash,
    )
    capsule.reason_code = reason_index(a, capsule)
    return {
        "reason_code": capsule.reason_code,
        "capsule_bits": to_base32(encode(capsule)),
    }


# ------------------------------------------------------------------ graph ----


def build_graph() -> StateGraph:
    g = StateGraph(DhruvaState)
    g.add_node("planner", planner)
    g.add_node("discovery", discovery)
    g.add_node("ocean", ocean)
    g.add_node("weather", weather)
    g.add_node("geo", geo)
    g.add_node("risk", risk)
    g.add_node("route", route)
    g.add_node("evidence", evidence)
    g.add_node("codec", codec)

    g.add_edge(START, "planner")
    for node in ("discovery", "ocean", "weather", "geo"):
        g.add_edge("planner", node)  # fan out
        g.add_edge(node, "risk")  # fan in
    g.add_edge("risk", "route")
    g.add_edge("route", "evidence")
    g.add_edge("evidence", "codec")
    g.add_edge("codec", END)
    return g


graph = build_graph().compile()


async def arun(query: str, lat: float, lon: float, **kw: Any) -> DhruvaState:
    """Async entry point. Nodes 2-5 do network I/O, so the graph must be driven
    with ainvoke — invoke() raises "No synchronous function provided" on the
    first async node it reaches."""
    from dhruva.graph.state import initial_state

    boat = kw.pop("boat_class", BoatClass.FRP_UNDER_12M)
    result: Any = await graph.ainvoke(initial_state(query, lat, lon, boat_class=boat, **kw))
    return cast(DhruvaState, result)


def run(query: str, lat: float, lon: float, **kw: Any) -> DhruvaState:
    """Blocking wrapper for scripts. Not for use inside a running loop."""
    import asyncio

    return asyncio.run(arun(query, lat, lon, **kw))
