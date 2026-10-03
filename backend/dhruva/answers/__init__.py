"""Spoken answers for the brief's example queries, beyond the verdict.

Each answer kind (avoid, productive, thunder, tide, route; query #7 lives in
analytics/decline.py and predates this) is the same shape: a rule picks
sentence keys, the values that fill them are evidence rows, and the words live
in data/phrases/<kind>.json in every pilot language. Nothing is free-written,
so the numeric firewall can trace every number, in the language asked.

An answer with no data says so in its own sentence ("no_data"); it never
leaves a gap that reads as calm.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dhruva.codec.codebook import load_lexicon
from dhruva.evidence.firewall import TIME_UNIT
from dhruva.evidence.schema import EvidenceItem

_DATA_DIR = Path(
    os.environ.get("DHRUVA_DATA_DIR", str(Path(__file__).resolve().parents[3] / "data"))
)
PHRASES_DIR = _DATA_DIR / "phrases"
IST = dt.timezone(dt.timedelta(hours=5, minutes=30))
M_PER_NM = 1852.0
EARTH_KM = 6371.0088


@dataclass(slots=True)
class Answer:
    kind: str
    status: str  # "ok" or "no_data"
    parts: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    evidence: list[EvidenceItem] = field(default_factory=list)
    # Anything the screen draws that is not a sentence (a route line).
    extra: dict[str, Any] = field(default_factory=dict)

    def add(self, part: str, key: str, **values: Any) -> None:
        self.parts.append((part, key, values))


@lru_cache(maxsize=16)
def phrases(kind: str) -> dict[str, Any]:
    return json.loads((PHRASES_DIR / f"{kind}.json").read_text(encoding="utf-8"))


def languages(kind: str) -> list[str]:
    return [k for k in phrases(kind) if not k.startswith("_")]


def compass_index(bearing: float) -> int:
    return round((bearing % 360) / 22.5) % 16


def clock(t: dt.datetime) -> str:
    """HH:MM in IST, the form the firewall reads as one time."""
    return t.astimezone(IST).strftime("%H:%M")


def decimal_hour(t: dt.datetime) -> float:
    local = t.astimezone(IST)
    return local.hour + local.minute / 60


def _fill(value: Any, lexicon: dict[str, Any], table: dict[str, Any], name: str) -> str:
    if isinstance(value, dict) and "bearing" in value:
        return lexicon["compass"][compass_index(float(value["bearing"]))]
    if isinstance(value, dict) and "word" in value:
        # A word from the phrase file's own lookup tables (country names, line kinds).
        return table.get(value["table"], {}).get(value["word"], value["word"])
    if isinstance(value, dt.datetime):
        return clock(value)
    if isinstance(value, float):
        return f"{value:g}"
    return str(value)


def render(answer: Answer, language: str) -> tuple[list[dict[str, str]], str]:
    """The sentences in the language asked, or English when the phrase file
    lacks it, plus which language was used. Always ends with the caveat."""
    table = phrases(answer.kind)
    if language not in table or language.startswith("_"):
        language = "en"
    lang = table[language]
    lexicon = load_lexicon(language)
    lines = []
    for part, key, values in answer.parts:
        fill = {k: _fill(v, lexicon, lang, k) for k, v in values.items()}
        lines.append({"part": part, "text": lang[key].format(**fill)})
    if "caveat" in lang:
        lines.append({"part": "caveat", "text": lang["caveat"]})
    return lines, language


def bearing_deg(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    x = math.sin(dl) * math.cos(p2)
    y = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(x, y)) + 360) % 360


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_KM * math.asin(math.sqrt(a))


def time_item(key: str, t: dt.datetime, dataset_id: str, cell: str, **kw: Any) -> EvidenceItem:
    """A clock time as an evidence row: decimal hours IST, so the firewall can
    match the HH:MM the sentence speaks."""
    return EvidenceItem(
        key=key,
        value=decimal_hour(t),
        unit=TIME_UNIT,
        dataset_id=dataset_id,
        cell=cell,
        valid_time=t.astimezone(dt.UTC),
        is_forecast=True,
        **kw,
    )
