"""The agent trace a person sees: the problem statement's nine agents, each with
whether it ran for this question and one line on what it found.

Built from the finished graph state, so it can only report what actually happened.
Every number in a line comes from an observation or the evidence bundle, never
from a model.

Seven of the nine are graph nodes. Visualization and user interaction are small
functions here, because their work is choosing what the screen shows and in which
language — the client draws it.
"""

from __future__ import annotations

from typing import Any

from dhruva.graph.state import DhruvaState, Intent

_LANGUAGE_NAMES = {
    "en": "English",
    "ta": "Tamil",
    "ml": "Malayalam",
    "hi": "Hindi",
    "or": "Odia",
    "te": "Telugu",
    "kn": "Kannada",
    "bn": "Bengali",
    "mr": "Marathi",
    "gu": "Gujarati",
}

# Which evidence cards and map layers answer each question type.
_VIEWS: dict[Intent, tuple[list[str], list[str]]] = {
    Intent.GO_NO_GO: (["verdict", "sea", "boundary"], ["boundaries"]),
    Intent.HAZARD: (["verdict", "hazards", "sea"], ["boundaries"]),
    Intent.FISHING_ZONE: (["verdict", "pfz", "ocean"], ["pfz", "sst", "chlorophyll"]),
    Intent.ROUTE: (["verdict", "sea", "boundary"], ["boundaries"]),
    Intent.BOUNDARY: (["boundary"], ["boundaries", "zones"]),
    Intent.CONDITIONS: (["sea", "ocean"], ["sst", "wave"]),
    Intent.DECLINE_ATTRIBUTION: (["ocean"], ["sst", "chlorophyll"]),
    Intent.EXPLAIN: (["evidence"], []),
}

_SOURCE_NAMES = {
    "open_meteo_marine": "Open-Meteo marine forecast",
    "open_meteo_forecast": "Open-Meteo forecast",
}


_INTENT_NAMES = {
    Intent.GO_NO_GO: "is it safe to go out",
    Intent.FISHING_ZONE: "where to fish",
    Intent.ROUTE: "which way to go",
    Intent.BOUNDARY: "how close is the boundary",
    Intent.HAZARD: "is there a warning",
    Intent.CONDITIONS: "what is the sea like",
    Intent.DECLINE_ATTRIBUTION: "why the catch changed",
    Intent.EXPLAIN: "how was this worked out",
}

_ZONE_NAMES = {
    "internal_waters": "internal waters",
    "eez": "India's EEZ",
    "territorial_sea_12nm": "territorial sea",
    "contiguous_24nm": "contiguous zone",
}


def _source(dataset_id: str) -> str:
    if dataset_id in _SOURCE_NAMES:
        return _SOURCE_NAMES[dataset_id]
    if dataset_id.startswith("cmems"):
        return "Copernicus Marine"
    return dataset_id


def _fmt(value: float) -> str:
    return f"{value:g}"


def _readings(state: DhruvaState, variables: set[str]) -> str:
    parts = []
    for o in state.get("observations", []):
        if o.variable.value in variables:
            name = o.variable.value.replace("_", " ")
            parts.append(f"{name} {_fmt(round(o.value, 2))} {o.unit} ({_source(o.dataset_id)})")
    return "; ".join(parts)


def visualization(intent: Intent | None) -> dict[str, list[str]]:
    """Agent 7: which cards and map layers answer this question."""
    cards, layers = _VIEWS.get(intent or Intent.CONDITIONS, (["sea"], []))
    return {"cards": cards, "layers": layers}


def build_trace(state: DhruvaState) -> list[dict[str, Any]]:
    plan = state.get("plan") or {}
    nodes = set(plan.get("nodes") or [])
    intent = state.get("intent")
    trace: list[dict[str, Any]] = []

    def add(agent: str, node: str, ran: bool, line: str) -> None:
        trace.append({"agent": agent, "node": node, "ran": ran, "line": line})

    reason = str(plan.get("reason", ""))
    asked = _INTENT_NAMES.get(intent, "a general sea question") if intent else "unclear"
    if reason.startswith("model "):
        how = "Gemini read the question as"
    else:
        cause = reason.split("(", 1)[1].rstrip(")") if "(" in reason else "no model"
        how = f"Keyword match ({cause}) read the question as"
    add("Planning", "planner", True, f"{how}: {asked}. Only the agents it needs will run.")

    datasets: dict[str, list[str]] = {}
    for z in state.get("zones", []):
        if z.get("kind") == "dataset_plan":
            datasets = z.get("datasets", {})
    eligible = sum(len(v) for v in datasets.values())
    add(
        "Marine data discovery",
        "discovery",
        True,
        f"{eligible} datasets can answer {', '.join(k.replace('_', ' ') for k in datasets)}"
        if datasets
        else "No dataset needed for this question",
    )

    weather = _readings(state, {"wave_height", "wave_period", "wind_speed", "wind_direction"})
    add(
        "Weather intelligence",
        "weather",
        "weather" in nodes,
        weather or ("Not needed for this question" if "weather" not in nodes else "No reading"),
    )

    ocean = _readings(state, {"sst", "chlorophyll", "current_speed", "current_direction"})
    add(
        "Ocean analytics",
        "ocean",
        "ocean" in nodes,
        ocean or ("Not needed for this question" if "ocean" not in nodes else "No reading"),
    )

    bounds = state.get("boundaries", [])
    zones = [z for z in state.get("zones", []) if z.get("kind") == "zone"]
    if "geo" not in nodes:
        geo_line = "Not needed for this question"
    elif bounds:
        b = bounds[0]
        inside = ", ".join(
            sorted(
                {_ZONE_NAMES.get(str(z.get("zone_type")), str(z.get("zone_type"))) for z in zones}
            )
        )
        geo_line = (
            f"{_fmt(round(b['distance_nm'], 1))} nm from {b['name']} "
            f"(Marine Regions, indicative)" + (f"; inside {inside}" if inside else "")
        )
    else:
        geo_line = "Boundary database not connected"
    if "geo" in nodes and (pfz := state.get("pfz")):
        # The centre is named, not measured: that distance is not in the evidence.
        where = f", off {pfz['centre_name']} landing centre" if pfz.get("centre_name") else ""
        geo_line += (
            f". Nearest fishing zone: INCOIS advisory of {pfz['issued_for']}, "
            f"{pfz['basis'] + ' line, ' if pfz.get('basis') else ''}"
            f"{_fmt(round(pfz['distance_nm'], 1))} nm away{where}"
        )
    elif "geo" in nodes and state.get("intent") is Intent.FISHING_ZONE:
        geo_line += ". No fresh INCOIS fishing-zone advisory within 60 nm"
    add("Geospatial reasoning", "geo", "geo" in nodes, geo_line)

    risk = state.get("risk_class")
    rules = state.get("fired_rules", [])
    add(
        "Risk assessment",
        "risk",
        True,
        f"Verdict {risk.value.replace('_', '-').upper() if risk else 'UNKNOWN'} from the rule "
        f"table ({', '.join(rules) or 'no rule fired'}). The model does not decide this.",
    )

    view = visualization(intent)
    add(
        "Visualization",
        "visualization",
        True,
        f"Shows {', '.join(view['cards'])}"
        + (f"; map layers {', '.join(view['layers'])}" if view["layers"] else ""),
    )

    ev = state.get("evidence", {})
    items = ev.get("items", [])
    add(
        "Reporting",
        "evidence",
        True,
        f"{len(items)} evidence rows, each with source and time; number check "
        f"{'passed' if state.get('firewall_passed') else 'failed, template used'}; "
        f"145-bit capsule built",
    )

    language = state.get("language", "en")
    add(
        "User interaction",
        "language",
        True,
        f"Answer in {_LANGUAGE_NAMES.get(language, language)}, from the shipped phrasebook, "
        f"so the phone can say it again with no network",
    )

    if plan.get("needs_route"):
        add("Route planning", "route", True, "Safe-route search is not built yet; no route given")
    return trace
