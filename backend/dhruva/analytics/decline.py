"""Query #7 — "why did fish productivity decline here?"

There is no catch data in DHRUVA, so this cannot say why a catch fell. What it
can say is whether the sea around the boat is unusual for the time of year: the
last 30 days in a box of about 20 x 20 km, against the same calendar window in
earlier years. A change counts as unusual only when it is larger than the
baseline's own year-to-year spread, because a sea that differs from last year
by less than last year differed from the year before is not news.

This module is the arithmetic and the choice of sentence. It fetches nothing
and has no clock, so every branch is testable with plain numbers; the fetch
lives in dhruva.analytics.baseline.

Honesty rules, from the 5-day plan and kept here rather than in a prompt:
- fewer than MIN_BASELINE_YEARS years with data for the box means No data;
- the answer says "possible", never "because", and never names a cause such as
  overfishing that the sea surface cannot show;
- every answer says it compares the sea, not the catch.
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import statistics
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from dhruva.codec.codebook import load_lexicon
from dhruva.sources.registry import Variable

# The plan: if fewer than 2 baseline years have data for the box, answer No data.
MIN_BASELINE_YEARS = 2
WINDOW_DAYS = 30
# Half the side of the box. 0.09 deg of latitude is 10 km; longitude is widened
# by 1/cos(lat) in box_around() so the box stays square on the ground.
HALF_BOX_KM = 10.0
KM_PER_DEG_LAT = 111.32

ANALYSED: tuple[Variable, ...] = (Variable.CHLOROPHYLL, Variable.SST)


@dataclass(frozen=True, slots=True)
class WindowMean:
    """One year's window, averaged over the box. mean is None when no day in
    the window had a finite value anywhere in the box (cloud, or no coverage)."""

    year: int
    start: dt.date
    end: dt.date
    mean: float | None
    days: int


@dataclass(frozen=True, slots=True)
class Change:
    """The current window against its baseline, for one variable."""

    variable: str
    unit: str
    dataset_id: str
    upstream_dataset_id: str
    window_start: dt.date
    window_end: dt.date
    current: float
    current_days: int
    baseline_mean: float
    baseline_spread: float
    baseline_years: list[int]
    change: float
    change_pct: float | None
    unusual: bool
    # Set when the baseline years come from a different product than the
    # current window (SST: the reprocessed record stops months behind today).
    baseline_dataset_id: str | None = None
    baseline_upstream_dataset_id: str | None = None

    @property
    def direction(self) -> str:
        """'up', 'down' or 'usual'. Only an unusual change has a direction."""
        if not self.unusual:
            return "usual"
        return "up" if self.change > 0 else "down"

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["window_start"] = self.window_start.isoformat()
        d["window_end"] = self.window_end.isoformat()
        d["direction"] = self.direction
        return d


def windows(end: dt.date, years_back: int) -> list[tuple[int, dt.date, dt.date]]:
    """The current WINDOW_DAYS window ending on `end`, then the same calendar
    window in each of the `years_back` earlier years. Newest first.

    29 February has no counterpart in most years; it is moved to 28 February
    rather than letting the window drift by a day.
    """
    out = []
    for back in range(years_back + 1):
        year = end.year - back
        try:
            e = end.replace(year=year)
        except ValueError:
            e = end.replace(year=year, day=28)
        out.append((year, e - dt.timedelta(days=WINDOW_DAYS - 1), e))
    return out


def box_around(lat: float, lon: float) -> tuple[float, float, float, float]:
    """(lat_min, lat_max, lon_min, lon_max) of the ~20 x 20 km box."""
    dlat = HALF_BOX_KM / KM_PER_DEG_LAT
    dlon = dlat / max(math.cos(math.radians(lat)), 0.01)
    return lat - dlat, lat + dlat, lon - dlon, lon + dlon


def compare(
    variable: Variable,
    unit: str,
    current: WindowMean,
    baseline: list[WindowMean],
    *,
    dataset_id: str,
    upstream_dataset_id: str,
    baseline_dataset_id: str | None = None,
    baseline_upstream_dataset_id: str | None = None,
) -> Change | None:
    """Current window against the baseline years, or None for No data.

    Spread is the sample standard deviation of the baseline years' means: the
    year-to-year variation the plan asks a change to exceed. It needs at least
    two years, which is also the plan's floor for answering at all.
    """
    if current.mean is None:
        return None
    usable = [w for w in baseline if w.mean is not None]
    if len(usable) < MIN_BASELINE_YEARS:
        return None
    means = [w.mean for w in usable if w.mean is not None]
    base = statistics.fmean(means)
    spread = statistics.stdev(means)
    change = current.mean - base
    return Change(
        variable=variable.value,
        unit=unit,
        dataset_id=dataset_id,
        upstream_dataset_id=upstream_dataset_id,
        window_start=current.start,
        window_end=current.end,
        current=current.mean,
        current_days=current.days,
        baseline_mean=base,
        baseline_spread=spread,
        baseline_years=sorted(w.year for w in usable),
        change=change,
        change_pct=(change / base * 100.0) if base else None,
        unusual=abs(change) > spread,
        baseline_dataset_id=baseline_dataset_id,
        baseline_upstream_dataset_id=baseline_upstream_dataset_id,
    )


# ------------------------------------------------------------- the answer ----


@dataclass(slots=True)
class DeclineAnswer:
    """The four-part answer, plus the caveat, as sentence keys with the values
    that fill them. Keys, not text: the same answer renders in any language the
    phrase file carries, and the numbers that fill it are exactly the ones the
    evidence bundle holds."""

    status: str  # "ok" or "no_data"
    parts: list[tuple[str, str, dict[str, Any]]] = field(default_factory=list)
    changes: dict[str, Change] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "parts": [{"part": p, "key": k, "values": v} for p, k, v in self.parts],
            "changes": {k: c.as_dict() for k, c in self.changes.items()},
        }


def _chl(value: float) -> float:
    return round(value, 2)


def _sst(value: float) -> float:
    return round(value, 1)


def answer(
    chl: Change | None,
    sst: Change | None,
    pfz: dict[str, Any] | None,
    *,
    no_go: bool = False,
) -> DeclineAnswer:
    """Pick the sentences. Rules, not free text: each branch names a phrase key.

    Chlorophyll is the lead variable, because surface plankton is the food chain
    the question is about. Without it there is no answer, even with SST: a
    warmer sea on its own says too little about fish to be worth a sentence that
    sounds like an explanation.

    NO-GO outranks everything: while the verdict is NO-GO the last part says so
    instead of pointing the boat at a fishing zone.
    """
    if chl is None:
        return DeclineAnswer(status="no_data", parts=[("normal", "no_data", {})])

    out = DeclineAnswer(status="ok", changes={"chlorophyll": chl})
    years = len(chl.baseline_years)
    out.parts.append(("normal", "normal_chl", {"usual": _chl(chl.baseline_mean)}))

    changed = {"up": "chl_higher", "down": "chl_lower", "usual": "chl_usual"}[chl.direction]
    out.parts.append(("changed", changed, {"now": _chl(chl.current), "years": years}))

    if sst is not None:
        out.changes["sst"] = sst
        sst_key = {"up": "sst_warmer", "down": "sst_cooler", "usual": "sst_usual"}[sst.direction]
        out.parts.append(("changed", sst_key, {"delta": _sst(abs(sst.change))}))

    # "Possible", never "because". One reason, from the strongest signal.
    if chl.direction == "down":
        reason = "reason_less_plankton"
    elif sst is not None and sst.direction == "up":
        reason = "reason_warmer"
    elif chl.direction == "up":
        reason = "reason_more_plankton"
    else:
        reason = "reason_sea_usual"
    out.parts.append(("reason", reason, {}))

    if no_go:
        out.parts.append(("todo", "todo_no_go", {}))
    elif pfz is not None:
        out.parts.append(
            (
                "todo",
                "todo_pfz",
                {"distance": round(float(pfz["distance_nm"])), "bearing": pfz["bearing_deg"]},
            )
        )
    else:
        out.parts.append(("todo", "todo_no_pfz", {}))
    return out


# --------------------------------------------------------------- phrasing ----

# Same root as the codebook (codec/codebook.py): DHRUVA_DATA_DIR in the
# container, the repo's data/ in a checkout.
_DATA_DIR = Path(
    os.environ.get("DHRUVA_DATA_DIR", str(Path(__file__).resolve().parents[3] / "data"))
)
PHRASES_PATH = _DATA_DIR / "phrases" / "decline.json"


@lru_cache(maxsize=2)
def phrases(path: str = str(PHRASES_PATH)) -> dict[str, dict[str, str]]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def languages() -> list[str]:
    return [k for k in phrases() if not k.startswith("_")]


def render(result: DeclineAnswer, language: str) -> list[dict[str, str]]:
    """Each part as text in the language, falling back to English for a
    language the phrase file does not carry. Always ends with the caveat.

    Compass words come from the capsule codebook's lexicon, so a direction
    reads the same here as in every other answer the phone speaks.
    """
    table = phrases()
    if language not in table or language.startswith("_"):
        language = "en"
    lang = table[language]
    lexicon = load_lexicon(language)
    lines = []
    for part, key, values in result.parts:
        fill = {k: (f"{v:g}" if isinstance(v, float) else v) for k, v in values.items()}
        if "bearing" in values:
            index = round((float(values["bearing"]) % 360) / 22.5) % 16
            fill["bearing"] = lexicon["compass"][index]
        lines.append({"part": part, "text": lang[key].format(**fill)})
    lines.append({"part": "caveat", "text": lang["caveat"]})
    return lines


# --------------------------------------------------------------- evidence ----


def evidence_items(result: DeclineAnswer, box: tuple[float, float, float, float]) -> list[Any]:
    """One row per number the answer can speak, so the numeric firewall can
    trace each of them. The SST difference is a row of its own, unsigned,
    because the sentence says warmer or cooler in words and speaks only the
    size; a signed row would fail the check on every cooler sea."""
    from dhruva.evidence.schema import EvidenceItem

    lat_min, lat_max, lon_min, lon_max = box
    cell = f"box {lat_min:.2f}-{lat_max:.2f}N, {lon_min:.2f}-{lon_max:.2f}E"
    centre_lat, centre_lon = (lat_min + lat_max) / 2, (lon_min + lon_max) / 2
    items: list[EvidenceItem] = []

    def row(c: Change, key: str, value: float, unit: str, *, baseline: bool = False) -> None:
        # A baseline row cites the product the baseline years came from; a row
        # comparing both (a change) cites both.
        dataset_id, upstream = c.dataset_id, c.upstream_dataset_id
        if baseline and c.baseline_dataset_id:
            if key.endswith("_baseline"):
                dataset_id = c.baseline_dataset_id
                upstream = c.baseline_upstream_dataset_id
            else:
                upstream = f"{c.upstream_dataset_id} vs {c.baseline_upstream_dataset_id}"
        items.append(
            EvidenceItem(
                key=key,
                value=value,
                unit=unit,
                dataset_id=dataset_id,
                upstream_dataset_id=upstream,
                cell=cell,
                cell_lat=centre_lat,
                cell_lon=centre_lon,
                valid_time=dt.datetime.combine(c.window_end, dt.time(), tzinfo=dt.UTC),
                window_start=c.window_start,
                window_end=c.window_end,
                baseline_years=c.baseline_years if baseline else None,
            )
        )

    chl = result.changes.get("chlorophyll")
    if chl is not None:
        row(chl, "chlorophyll_30d", chl.current, chl.unit)
        row(chl, "chlorophyll_baseline", chl.baseline_mean, chl.unit, baseline=True)
        if chl.change_pct is not None:
            row(chl, "chlorophyll_change_pct", chl.change_pct, "%", baseline=True)
        row(chl, "baseline_years", float(len(chl.baseline_years)), "years", baseline=True)
    sst = result.changes.get("sst")
    if sst is not None:
        row(sst, "sst_30d", sst.current, sst.unit)
        row(sst, "sst_baseline", sst.baseline_mean, sst.unit, baseline=True)
        row(sst, "sst_difference", abs(sst.change), sst.unit, baseline=True)
    return items
