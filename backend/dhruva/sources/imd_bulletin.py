"""IMD cyclone bulletins as hazard inputs: live ones from the feed, and past
ones replayed with a storm. Both are read by the same parser
(sources/imd_parser.py) from IMD's own PDF; no position is typed by hand.

Live (live_status): the newest bulletin of each system that is still in force
(until its next bulletin is due, plus a grace period). For a boat in that
system's sea:
- a cyclonic disturbance (Depression and above) with a readable centre gives
  the cyclone distance, measured from where the forecast track puts the system
  at the hour asked about, and the absolute override takes it from there;
- a bulletin that could not be read, or whose fishermen warning names the
  boat's own coast while the centre is far away, adds an alert the risk engine
  does not recognise, which forces at least CAUTION (default-deny) and shows
  the bulletin's link. A warning is never dropped because it did not parse;
- with nothing in force the answer says "No active IMD cyclone bulletin as of
  <when the listing was last checked>", never "no danger".

Replay (cyclone_source): a stored past bulletin named by id, which only speaks
for the hours around its centre time and refuses any other.
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
from dhruva.sources.imd_parser import CYCLONES, DISTURBANCES, IST, parse_pdf

_DATA = Path(os.environ.get("DHRUVA_DATA_DIR", "data"))
_PATH = _DATA / "imd" / "bulletins.json"
EARTH_KM = 6371.0088
# How far from the bulletin's centre time a replay may be asked about.
VALID_WITHIN = dt.timedelta(hours=6)
# A live bulletin stays in force until its next one is due, plus this grace:
# IMD bulletins are often an hour or two late, and a lapse must not read as
# an all-clear.
GRACE = dt.timedelta(hours=3)
# A bulletin that names no next issue (a final one) speaks for this long.
NO_NEXT = dt.timedelta(hours=6)
# The listing is checked every 30 minutes; older than this, say so.
STALE_AFTER = dt.timedelta(hours=2)
# The live feed answers for the present and the forecast ahead of it, not for
# a past storm (that is what a replayed bulletin is for).
LIVE_WINDOW = (dt.timedelta(hours=-6), dt.timedelta(hours=72))

ALERT_UNREADABLE = "imd_bulletin_unreadable"
ALERT_COAST = "imd_fishermen_warning"


class BulletinError(ValueError):
    pass


def _km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def _resolve(local: str) -> Path:
    """A stored path is relative to the repo root ("data/imd/..."); in the
    container the data dir is DHRUVA_DATA_DIR."""
    p = Path(local)
    if p.exists():
        return p
    parts = p.parts[1:] if p.parts and p.parts[0] == "data" else p.parts
    return _DATA.joinpath(*parts)


@lru_cache(maxsize=16)
def _parse_local(path: str, sha256: str) -> dict[str, Any]:
    """Parse a stored PDF once per content hash."""
    data = Path(path).read_bytes()
    return parse_pdf(data).as_dict()


def bulletins() -> dict[str, dict[str, Any]]:
    """Replay bulletins: provenance from bulletins.json, every field from the
    PDF through the parser."""
    if not _PATH.exists():
        return {}
    out = {}
    for bid, meta in json.loads(_PATH.read_text(encoding="utf-8")).items():
        path = _resolve(meta["local_copy"])
        out[bid] = {**_parse_local(str(path), meta.get("sha256", "")), **meta}
    return out


def _title(b: dict[str, Any]) -> str:
    return f"National Bulletin No. {b.get('number')} ({b.get('system_id')})"


def _source(b: dict[str, Any], lat: float, lon: float, at: dt.datetime, plat: float, plon: float):
    return {
        "issuer": b.get("issuer", "IMD, RSMC Tropical Cyclones New Delhi"),
        "title": _title(b),
        "system": f"{b.get('category')} {b['name']}" if b.get("name") else b.get("category"),
        "category": b.get("category"),
        "system_id": b.get("system_id"),
        "issued_at": b.get("issued_at"),
        "centre_at": at.isoformat(),
        "lat": plat,
        "lon": plon,
        "source_url": b.get("source_url"),
        "local_copy": b.get("local_copy"),
        "sha256": b.get("sha256"),
        "fishermen_warning": b.get("fishermen_warning"),
        "distance_km": _km(lat, lon, plat, plon),
    }


def cyclone_source(
    bulletin_id: str, lat: float, lon: float, when: dt.datetime | None
) -> dict[str, Any]:
    """A replayed bulletin, with this point's distance from its centre. Raises
    BulletinError for an unknown bulletin, one the parser could not read, or a
    time it does not cover."""
    b = bulletins().get(bulletin_id)
    if b is None:
        raise BulletinError(f"unknown bulletin {bulletin_id!r}")
    if b.get("lat") is None or b.get("centre_at") is None:
        raise BulletinError(
            f"{bulletin_id}: the parser could not read a centre ({b.get('missing')})"
        )
    centre_at = dt.datetime.fromisoformat(b["centre_at"])
    if when is None:
        raise BulletinError("a bulletin needs the time it is asked about")
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    if abs(when - centre_at) > VALID_WITHIN:
        raise BulletinError(
            f"{_title(b)} gives the centre at {b['centre_at']}, not {when.isoformat()}"
        )
    return {**_source(b, lat, lon, centre_at, b["lat"], b["lon"]), "id": bulletin_id}


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


# ------------------------------------------------------------------ live ----


def boat_basins(lat: float, lon: float) -> set[str]:
    """Which IMD basin's bulletins concern a boat here. The southern tip
    (Comorin, Gulf of Mannar) answers to both, so overlap errs towards warning."""
    out = set()
    if lon > 77.3:
        out.add("BOB")
    if lon < 78.2:
        out.add("ARB")
    return out


# Words a fishermen warning uses for a coast, by stretch of coast. A warning
# names the boat's coast when every word of any one entry appears in it.
# Coarse by design: a match can only add CAUTION, never remove one.
_COASTS: list[tuple[tuple[float, float, float, float], list[tuple[str, ...]]]] = [
    # (lat_min, lat_max, lon_min, lon_max), terms
    (
        (7.5, 13.6, 77.3, 81.0),
        [
            ("tamil nadu",),
            ("tamilnadu",),
            ("puducherry",),
            ("karaikal",),
            ("gulf of mannar",),
            ("comorin",),
            ("southwest", "bay of bengal"),
            ("sri lanka",),
        ],
    ),
    (
        (13.6, 19.2, 79.5, 85.5),
        [("andhra",), ("yanam",), ("westcentral", "bay of bengal"), ("southwest", "bay of bengal")],
    ),
    (
        (19.2, 21.7, 84.0, 88.0),
        [
            ("odisha",),
            ("orissa",),
            ("northwest", "bay of bengal"),
            ("westcentral", "bay of bengal"),
        ],
    ),
    (
        (21.4, 23.0, 86.5, 90.0),
        [
            ("west bengal",),
            ("northwest", "bay of bengal"),
            ("north bay of bengal",),
            ("bangladesh",),
        ],
    ),
    ((5.5, 14.5, 91.5, 94.5), [("andaman",), ("nicobar",)]),
    (
        (8.0, 12.8, 74.5, 77.6),
        [("kerala",), ("comorin",), ("lakshadweep",), ("southeast", "arabian sea")],
    ),
    ((8.0, 12.5, 71.0, 74.5), [("lakshadweep",), ("southeast", "arabian sea")]),
    (
        (12.8, 15.9, 73.4, 75.2),
        [("karnataka",), ("goa",), ("eastcentral", "arabian sea"), ("southeast", "arabian sea")],
    ),
    (
        (15.9, 20.3, 72.4, 73.8),
        [
            ("maharashtra",),
            ("konkan",),
            ("eastcentral", "arabian sea"),
            ("northeast", "arabian sea"),
        ],
    ),
    (
        (20.3, 24.5, 67.5, 73.0),
        [("gujarat",), ("saurashtra",), ("kutch",), ("northeast", "arabian sea")],
    ),
]


def names_coast(warning: str | None, lat: float, lon: float) -> bool:
    if not warning:
        return False
    text = warning.lower()
    for (la0, la1, lo0, lo1), terms in _COASTS:
        here = la0 <= lat <= la1 and lo0 <= lon <= lo1
        if here and any(all(w in text for w in entry) for entry in terms):
            return True
    return False


def valid_until(b: dict[str, Any]) -> dt.datetime | None:
    if b.get("next_issue_at"):
        return dt.datetime.fromisoformat(b["next_issue_at"]) + GRACE
    if b.get("issued_at"):
        return dt.datetime.fromisoformat(b["issued_at"]) + NO_NEXT
    return None


def _in_force(feed: dict[str, Any], now: dt.datetime) -> list[dict[str, Any]]:
    """The newest bulletin of each system, if it is still in force. An
    unreadable bulletin with no system id still counts, keyed by itself."""
    newest: dict[str, dict[str, Any]] = {}
    for key, b in feed.get("bulletins", {}).items():
        issued = b.get("issued_at")
        if issued is None:
            # Not even the header could be read: in force from when it was
            # fetched, for the default span.
            issued = b.get("fetched_at")
            b = {**b, "issued_at": issued}
        sys_key = b.get("system_id") or f"unknown:{key}"
        if sys_key not in newest or issued > newest[sys_key]["issued_at"]:
            newest[sys_key] = b
    out = []
    for b in newest.values():
        until = valid_until(b)
        if until is not None and dt.datetime.fromisoformat(b["issued_at"]) <= now <= until:
            out.append({**b, "valid_until": until.isoformat()})
    return out


def _position_at(b: dict[str, Any], when: dt.datetime) -> tuple[dt.datetime, float, float] | None:
    """Where IMD puts the system at `when`: the forecast track point nearest in
    time, else the analysed centre."""
    track = b.get("track") or []
    if track:
        p = min(track, key=lambda p: abs(dt.datetime.fromisoformat(p["at"]) - when))
        return dt.datetime.fromisoformat(p["at"]), p["lat"], p["lon"]
    if b.get("lat") is not None and b.get("centre_at"):
        return dt.datetime.fromisoformat(b["centre_at"]), b["lat"], b["lon"]
    return None


def _summary(b: dict[str, Any]) -> dict[str, Any]:
    return {
        "title": _title(b) if b.get("number") else "IMD National Bulletin",
        "system_id": b.get("system_id"),
        "name": b.get("name"),
        "category": b.get("category"),
        "status": b.get("status"),
        "issued_at": b.get("issued_at"),
        "valid_until": b.get("valid_until"),
        "source_url": b.get("source_url"),
        "fishermen_warning": b.get("fishermen_warning"),
    }


def live_status(
    lat: float,
    lon: float,
    when: dt.datetime | None,
    *,
    now: dt.datetime | None = None,
    feed: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """What IMD's bulletins in force say for this boat at this hour.

    Returns a dict with "status" ("active", "none" or "unchecked"), a
    "message" for the screen, "bulletins" (summaries, with links), and the
    hazard inputs: "cyclone" (a cyclone_source dict, or None) and "alerts".
    """
    from dhruva.sources.imd_feed import load_feed

    now = now or dt.datetime.now(dt.UTC)
    when = when or now
    feed = load_feed() if feed is None else feed
    checked = feed.get("checked_at")
    checked_at = dt.datetime.fromisoformat(checked) if checked else None
    out: dict[str, Any] = {
        "checked_at": checked,
        "bulletins": [],
        "cyclone": None,
        "alerts": [],
    }
    if not (LIVE_WINDOW[0] <= when - now <= LIVE_WINDOW[1]):
        return {**out, "status": "not_applicable", "message": None}
    if checked_at is None:
        return {
            **out,
            "status": "unchecked",
            "message": "IMD cyclone bulletins have not been checked yet.",
        }

    basins = boat_basins(lat, lon)
    nearest: dict[str, Any] | None = None
    for b in _in_force(feed, now):
        if b.get("basin") and b["basin"] not in basins:
            continue
        out["bulletins"].append(_summary(b))
        pos = _position_at(b, when) if b.get("category") in DISTURBANCES else None
        readable = b.get("status") == "ok" or (pos is not None and b.get("category"))
        if not readable:
            out["alerts"].append(ALERT_UNREADABLE)
            continue
        if pos is not None:
            at, plat, plon = pos
            src = _source(b, lat, lon, at, plat, plon)
            if nearest is None or src["distance_km"] < nearest["distance_km"]:
                nearest = src
            if src["distance_km"] > 300 and names_coast(b.get("fishermen_warning"), lat, lon):
                out["alerts"].append(ALERT_COAST)
        elif names_coast(b.get("fishermen_warning"), lat, lon):
            out["alerts"].append(ALERT_COAST)
    out["cyclone"] = nearest
    out["alerts"] = sorted(set(out["alerts"]))

    stale = now - checked_at > STALE_AFTER
    as_of = checked_at.astimezone(IST).strftime("%-d %b %H:%M IST")
    if out["bulletins"]:
        out["status"] = "active"
        out["message"] = "Official warning: read the IMD bulletin."
    else:
        out["status"] = "none"
        out["message"] = f"No active IMD cyclone bulletin as of {as_of}."
    if stale:
        out["message"] += f" IMD's bulletin list has not been checked since {as_of}."
    return out


def is_cyclone(category: str | None) -> bool:
    return category in CYCLONES


def overall_status(
    *, now: dt.datetime | None = None, feed: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Every bulletin in force, any basin, for the shore console: what is
    active, where IMD puts its centre now, and when the list was checked."""
    from dhruva.sources.imd_feed import load_feed

    now = now or dt.datetime.now(dt.UTC)
    feed = load_feed() if feed is None else feed
    checked = feed.get("checked_at")
    in_force = []
    for b in _in_force(feed, now) if checked else []:
        pos = _position_at(b, now) if b.get("category") in DISTURBANCES else None
        in_force.append(
            {
                **_summary(b),
                "centre": {"lat": pos[1], "lon": pos[2], "at": pos[0].isoformat()} if pos else None,
            }
        )
    if checked is None:
        message = "IMD cyclone bulletins have not been checked yet."
    else:
        as_of = dt.datetime.fromisoformat(checked).astimezone(IST).strftime("%-d %b %H:%M IST")
        plural = "s" if len(in_force) != 1 else ""
        message = (
            f"{len(in_force)} IMD bulletin{plural} in force as of {as_of}."
            if in_force
            else f"No active IMD cyclone bulletin as of {as_of}."
        )
    return {
        "status": "active" if in_force else ("none" if checked else "unchecked"),
        "checked_at": checked,
        "error": feed.get("error"),
        "message": message,
        "bulletins": in_force,
        "source": "https://rsmcnewdelhi.imd.gov.in/ (National Bulletin archive, read, attributed)",
    }
