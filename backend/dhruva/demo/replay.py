"""Recorded runs, replayed when a live source fails or when the demo asks for it.

A recording is a real /advisory response captured by scripts/record_demo.py: the
same numbers, sources and capsule a live run produced, with the time it was
recorded. Nothing here is invented, and a replayed response always carries
`recorded_at` so the screen can say so.

DHRUVA_DEMO selects the mode:

    off       always live
    fallback  live; a recording answers only when the live run fails (default)
    replay    a matching recording answers first; live for anything unrecorded
"""

from __future__ import annotations

import datetime as dt
import json
import os
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
# Default path works both from the repo root and in the api container, where
# data/ is mounted at /app/data.
_DEFAULT = Path(os.environ.get("DHRUVA_DATA_DIR", "data")) / "demo" / "recordings.json"


def mode() -> str:
    m = os.environ.get("DHRUVA_DEMO", "fallback").strip().lower()
    return m if m in ("off", "fallback", "replay") else "fallback"


def when_key(when: dt.datetime | None, now: dt.datetime | None = None) -> str:
    """How a request's departure time is matched. "Tomorrow 5 AM" is a different
    instant every day, so near-future times match on their IST hour; a past date
    (a replayed storm) matches on the date and hour itself."""
    if when is None:
        return "now"
    now = now or dt.datetime.now(dt.UTC)
    if when.tzinfo is None:
        when = when.replace(tzinfo=dt.UTC)
    if when < now - dt.timedelta(days=2):
        return when.astimezone(dt.UTC).strftime("%Y-%m-%dT%H")
    return f"ist{when.astimezone(IST).hour:02d}"


def key(
    query: str,
    language: str,
    lat: float,
    lon: float,
    boat_class: str,
    when: dt.datetime | None,
    test_cyclone_km: float | None,
    alerts: list[str] | None = None,
    bulletin: str | None = None,
) -> str:
    q = " ".join(unicodedata.normalize("NFC", query).casefold().split())
    cyc = "" if test_cyclone_km is None else f"{round(test_cyclone_km)}"
    k = f"{q}|{language}|{lat:.2f}|{lon:.2f}|{boat_class}|{when_key(when)}|{cyc}"
    # Appended only when present, so recordings made without alerts keep their keys.
    if alerts:
        k += "|alerts=" + ",".join(sorted({a.strip().lower() for a in alerts}))
    if bulletin:
        k += f"|bulletin={bulletin}"
    return k


@lru_cache(maxsize=1)
def _load(path: str, mtime: float) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def recordings(path: Path = _DEFAULT) -> dict[str, Any]:
    if not path.exists():
        return {"recorded_at": None, "entries": {}}
    return _load(str(path), path.stat().st_mtime)


def find(k: str, path: Path = _DEFAULT) -> dict[str, Any] | None:
    rec = recordings(path)
    entry = rec.get("entries", {}).get(k)
    if entry is None:
        return None
    return {**entry, "recorded_at": entry.get("recorded_at") or rec.get("recorded_at")}


def live_failed(state: dict[str, Any]) -> bool:
    """The live run could not answer the question asked. Either every source
    failed (nothing observed, errors recorded), or the question's own answer
    (query #7, or one of the brief's other queries) came back No data because
    its sources failed. The graph's live answer is honest, but a recording of the
    same question is more useful to show, labelled as a recording."""
    if not state.get("errors"):
        return False
    if not state.get("observations"):
        return True
    answers = (state.get("decline_answer"), state.get("answer"))
    return any((a or {}).get("status") == "no_data" for a in answers)
