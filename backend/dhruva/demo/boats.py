"""Demo boats for the shore console's "Warn boats" view.

These are not vessels and not tracks: they are named positions on real fishing
grounds, used to show one warning becoming a different message for each boat.
Every one is labelled a demo boat wherever it appears. Each was checked on
28 Sep 2026 to fall inside India's territorial sea (Marine Regions, via PostGIS),
so none sits on land or across a boundary.
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter

router = APIRouter(prefix="/demo", tags=["demo"])

DEMO_BOATS: list[dict[str, Any]] = [
    {"name": "off Pulicat", "lat": 13.45, "lon": 80.40},
    {"name": "off Kasimedu, Chennai", "lat": 13.12, "lon": 80.40},
    {"name": "off Mamallapuram", "lat": 12.60, "lon": 80.30},
    {"name": "off Puducherry", "lat": 11.95, "lon": 79.95},
    {"name": "off Cuddalore", "lat": 11.70, "lon": 79.90},
    {"name": "off Nagapattinam", "lat": 10.75, "lon": 80.00},
    {"name": "off Kodiyakarai", "lat": 10.20, "lon": 80.00},
    {"name": "off Thoothukudi", "lat": 8.75, "lon": 78.35},
    {"name": "off Kanyakumari", "lat": 7.95, "lon": 77.55},
    {"name": "off Kochi", "lat": 9.95, "lon": 76.05},
]


@router.get("/boats")
def get_demo_boats() -> list[dict[str, Any]]:
    return [{**b, "demo": True, "boat_class": "frp_under_12m"} for b in DEMO_BOATS]
