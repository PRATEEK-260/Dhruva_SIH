#!/usr/bin/env python
"""Run one question through the real graph and print what each node did.

Nothing here is staged: the planner calls Gemini (or says it fell back), the
fetch nodes hit Open-Meteo and Copernicus live, geo queries PostGIS, and the
verdict comes from the rule table. The output is the demo's agent trace.

    set -a; . ./.env; set +a
    export DHRUVA_DSN=postgresql://...        # geo is skipped without it
    PYTHONPATH=backend .venv/bin/python scripts/trace_query.py \
        "Is it safe to go fishing this morning?" --lat 11.05 --lon 79.95

Run from the repo root: the registry and the Zarr cache resolve against it.
"""

from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import time
import warnings
from typing import Any

from dhruva.graph.build import graph
from dhruva.graph.state import BoatClass, initial_state

# The copernicusmarine toolbox logs every dataset-version pick at INFO, and zarr
# warns about its own v3 metadata; neither is part of the trace.
logging.getLogger("copernicusmarine").setLevel(logging.ERROR)
warnings.filterwarnings("ignore", message="Consolidated metadata")

TEST_CYCLONE = False  # set from --test-cyclone-km, so the evidence row is labelled too

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
W = 11  # node-name column


def _line(t0: float, node: str, text: str) -> None:
    print(f"[{time.perf_counter() - t0:6.1f} s] {node:<{W}}{text}")


def _more(text: str) -> None:
    print(f"{'':>{10 + W}}{text}")


def _hemi(lat: float, lon: float) -> str:
    return f"{abs(lat):.2f}{'N' if lat >= 0 else 'S'} {abs(lon):.2f}{'E' if lon >= 0 else 'W'}"


def _show(t0: float, node: str, out: dict[str, Any]) -> None:
    if not out:
        _line(t0, node, "not in plan, skipped" if node != "route" else "no route asked")
        return

    if node == "planner":
        plan = out["plan"]
        _line(t0, node, f"intent {out['intent'].value}")
        _more(f"decided by: {plan['reason']}")
        _more(f"nodes: {', '.join(plan['nodes'])}")
        _more(f"variables: {', '.join(v.value for v in plan['variables'])}")

    elif node == "discovery":
        plan = next(z for z in out["zones"] if z.get("kind") == "dataset_plan")
        _line(t0, node, "eligible datasets per variable")
        for var, ids in plan["datasets"].items():
            _more(f"{var:<16} {', '.join(ids) or '(none)'}")

    elif node == "geo":
        zones = [z for z in out.get("zones", []) if z.get("kind") == "zone"]
        _line(t0, node, "PostGIS, Marine Regions boundaries (indicative, not legal)")
        for z in zones:
            _more(f"inside  {z.get('zone_type')}: {z.get('name')}")
        for b in out.get("boundaries", []):
            _more(f"nearest {b['line_type']}: {b['name']}, {b['distance_nm']} nm")

    elif node in ("ocean", "weather"):
        _line(t0, node, "live fetch")
        for o in out.get("observations", []):
            kind = "forecast" if o.is_forecast else "analysis"
            _more(
                f"{o.variable.value:<16} {o.value:>7} {o.unit:<7}{o.dataset_id:<21}"
                f"cell {_hemi(o.cell_lat, o.cell_lon)} ({o.offset_km:.1f} km off), "
                f"valid {o.valid_time:%d %b %H:%MZ}, {kind}"
            )
        for e in out.get("errors", []):
            _more(f"x {e.dataset_id} failed: {e.error[:70]}")

    elif node == "risk":
        _line(t0, node, f"verdict {out['risk_class'].value.upper()}")
        _more(f"rules fired: {', '.join(out['fired_rules']) or '(none)'}")
        if out.get("hazard_flags"):
            _more(f"hazards: {', '.join(out['hazard_flags'])}")

    elif node == "evidence":
        ev = out["evidence"]
        _line(t0, node, f"{len(ev['items'])} items, each tied to a dataset, cell and time")
        for i in ev["items"]:
            rule = f"rule {i['rule_id']} (threshold {i['threshold']})" if i.get("rule_id") else ""
            test = "  <- TEST INPUT" if i["key"] == "cyclone_distance" and TEST_CYCLONE else ""
            _more(f"{i['key']:<16} {i['value']:>7} {i['unit']:<7}{i['dataset_id']:<21}{rule}{test}")
        if ev.get("provisional_thresholds"):
            _more("thresholds: PROVISIONAL engineering placeholders, not INCOIS criteria")
        verdict = "passed" if out["firewall_passed"] else f"FAILED {out['firewall_violations']}"
        _more(f"numeric firewall: {verdict}")
        _more(f'narration: "{out["narration"]}"')

    elif node == "codec":
        _line(t0, node, f"capsule {out['capsule_bits']}  (145 bits, base32)")
        _more(f"reason code {out['reason_code']}")

    else:
        _line(t0, node, str(out)[:100])


async def main() -> None:
    ap = argparse.ArgumentParser(description="Trace one question through the DHRUVA graph.")
    ap.add_argument("query")
    ap.add_argument("--lat", type=float, default=11.05)
    ap.add_argument("--lon", type=float, default=79.95)
    ap.add_argument("--boat", choices=[b.value for b in BoatClass], default="frp_under_12m")
    ap.add_argument(
        "--test-cyclone-km",
        type=float,
        help="TEST INPUT: pretend a cyclone warning is active this far away. No live feed yet.",
    )
    args = ap.parse_args()

    now = dt.datetime.now(IST)
    print(f"DHRUVA agent trace   {now:%d %b %Y %H:%M IST}")
    print(f'query   "{args.query}"')
    print(f"at      {_hemi(args.lat, args.lon)}   boat {args.boat}")
    if args.test_cyclone_km is not None:
        global TEST_CYCLONE
        TEST_CYCLONE = True
        print(
            f"TEST INPUT  simulated cyclone warning, centre {args.test_cyclone_km:g} km away."
            " Not a live IMD bulletin."
        )
    print("-" * 96)

    t0 = time.perf_counter()
    state = initial_state(
        args.query,
        args.lat,
        args.lon,
        boat_class=BoatClass(args.boat),
        cyclone_distance_km=args.test_cyclone_km,
    )
    async for update in graph.astream(state, stream_mode="updates"):
        for node, out in update.items():
            _show(t0, node, out or {})
    print("-" * 96)
    print("Advisory only. Follow official INCOIS and IMD warnings.")


if __name__ == "__main__":
    asyncio.run(main())
