"""Past IMD cyclone bulletins, stored as dated records with their source.

There is no live IMD feed yet. A replayed storm can name a real bulletin
instead of a test input, and the cyclone distance then comes from the centre
IMD published, with the bulletin's own times on the evidence row. A bulletin
only speaks for the hours around its centre time: asked about another moment,
it refuses rather than let an old position stand in for a new one.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from functools import lru_cache
from pathlib import Path
from typing import Any

from dhruva.evidence.schema import EvidenceItem

_PATH = Path(os.environ.get("DHRUVA_DATA_DIR", "data")) / "imd" / "bulletins.json"
EARTH_KM = 6371.0088
# How far from the bulletin's centre time a request may be and still use it.
VALID_WITHIN = dt.timedelta(hours=6)


class BulletinError(ValueError):
    pass


def bulletins() -> dict[str, dict[str, Any]]:
    return _load(str(_PATH))


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, dict[str, Any]]:
    p = Path(path)
    if not p.exists():
        return {}
    data: dict[str, dict[str, Any]] = json.loads(p.read_text(encoding="utf-8"))
    return data


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def cyclone_source(
    bulletin_id: str, lat: float, lon: float, when: dt.datetime | None
) -> dict[str, Any]:
    """The bulletin, with this point's distance from its centre. Raises
    BulletinError for an unknown bulletin or a time it does not cover."""
    b = bulletins().get(bulletin_id)
    if b is None:
        raise BulletinError(f"unknown bulletin {bulletin_id!r}")
    centre_at = dt.datetime.fromisoformat(b["centre_at"])
    if when is None:
        raise BulletinError("a bulletin needs the time it is asked about")
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    if abs(when - centre_at) > VALID_WITHIN:
        raise BulletinError(
            f"{b['title']} gives the centre at {b['centre_at']}, not {when.isoformat()}"
        )
    return {**b, "id": bulletin_id, "distance_km": _km(lat, lon, b["lat"], b["lon"])}


def cyclone_item(src: dict[str, Any]) -> EvidenceItem:
    """The distance to the IMD centre as an evidence row: the cell is the centre
    IMD published and valid_time is the time that centre was for."""
    return EvidenceItem(
        key="cyclone_distance",
        value=float(src["distance_km"]),
        unit="km",
        dataset_id="imd_rsmc_bulletin",
        upstream_dataset_id=f"{src['issuer']}, {src['title']}, issued {src['issued_at']}",
        cell=f"{src['lat']:.1f}N, {src['lon']:.1f}E",
        cell_lat=src["lat"],
        cell_lon=src["lon"],
        valid_time=dt.datetime.fromisoformat(src["centre_at"]),
        is_forecast=False,
    )
