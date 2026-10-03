"""Read an IMD National Bulletin (RSMC New Delhi) out of its PDF.

IMD publishes no feed. Each bulletin is a PDF at a stable path under
rsmcnewdelhi.imd.gov.in/uploads/archive/1/, listed on the National Bulletin
archive page (sources/imd_feed.py fetches it). This module turns one PDF's text
into the fields the risk engine needs: the system, its category, where IMD put
its centre and when, the forecast track, the fishermen warning, and when the
next bulletin is due (which is how long this one speaks for).

It is pure: bytes or text in, a ParsedBulletin out. Nothing here fetches, and
nothing here decides a verdict.

The bulletins are typed by hand from a template, so the wording drifts: "Sub:"
or "Subject:", "centred" or "centered", "Long itude" split by the PDF, numbers
broken as "15. 6", track rows with or without "kmph ... gusting to". The
patterns below were written against real bulletins (Michaung, Dec 2023; the
BOB/06 and BOB/07 systems of Sep 2026) and every one is tested against them.

A field that cannot be read is reported, never guessed. A bulletin with no
readable body text at all (IMD sometimes uploads a scan) parses as
status "unreadable", and the caller must then treat the area as at least
CAUTION and show the link: a warning is never dropped because it did not parse.
"""

from __future__ import annotations

import datetime as dt
import io
import re
from dataclasses import asdict, dataclass, field
from typing import Any

IST = dt.timezone(dt.timedelta(hours=5, minutes=30))

# Strongest first, so "Severe Cyclonic Storm" is not read as "Cyclonic Storm".
CATEGORIES: tuple[str, ...] = (
    "Super Cyclonic Storm",
    "Extremely Severe Cyclonic Storm",
    "Very Severe Cyclonic Storm",
    "Severe Cyclonic Storm",
    "Cyclonic Storm",
    "Deep Depression",
    "Depression",
    "Well Marked Low Pressure Area",
    "Low Pressure Area",
)
# IMD's cyclonic disturbances start at Depression; a low is not one.
DISTURBANCES = frozenset(CATEGORIES[:7])
CYCLONES = frozenset(CATEGORIES[:5])

_MONTHS = {
    m: i
    for i, m in enumerate(
        (
            "january",
            "february",
            "march",
            "april",
            "may",
            "june",
            "july",
            "august",
            "september",
            "october",
            "november",
            "december",
        ),
        start=1,
    )
}
_CATEGORY_RE = "|".join(re.escape(c) for c in CATEGORIES)


@dataclass(frozen=True, slots=True)
class TrackPoint:
    at: dt.datetime  # UTC
    lat: float
    lon: float
    wind_kmph: tuple[int, int] | None
    gust_kmph: int | None
    category: str | None


@dataclass(slots=True)
class ParsedBulletin:
    status: str  # "ok", "partial" (some fields missing) or "unreadable"
    number: int | None = None
    system_id: str | None = None  # e.g. "BOB/07/2026"
    basin: str | None = None  # "BOB" (Bay of Bengal) or "ARB" (Arabian Sea)
    name: str | None = None  # e.g. "MICHAUNG"; depressions have none
    category: str | None = None
    issued_at: dt.datetime | None = None  # UTC
    centre_at: dt.datetime | None = None  # UTC
    lat: float | None = None
    lon: float | None = None
    track: list[TrackPoint] = field(default_factory=list)
    subject: str | None = None
    fishermen_warning: str | None = None
    next_issue_at: dt.datetime | None = None  # UTC
    missing: list[str] = field(default_factory=list)

    @property
    def is_disturbance(self) -> bool:
        return self.category in DISTURBANCES

    def as_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("issued_at", "centre_at", "next_issue_at"):
            d[k] = d[k].isoformat() if d[k] else None
        d["track"] = [
            {**asdict(p), "at": p.at.isoformat(), "wind_kmph": list(p.wind_kmph or []) or None}
            for p in self.track
        ]
        return d


def pdf_text(data: bytes) -> str:
    """Every page's text. Raises on a file that is not a readable PDF."""
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def normalise(text: str) -> str:
    """One line, single spaces, and the PDF's own breakage mended."""
    t = re.sub(r"\s+", " ", text)
    t = re.sub(r"(\d)\.\s+(\d)", r"\1.\2", t)  # "15. 6" -> "15.6"
    t = re.sub(r"L\s*o\s*n\s*g\s*i\s*t\s*u\s*d\s*e", "Longitude", t, flags=re.I)
    t = re.sub(r"L\s*a\s*t\s*i\s*t\s*u\s*d\s*e", "Latitude", t, flags=re.I)
    t = t.replace("“", '"').replace("”", '"')
    return t


def _ist(day: dt.date, hhmm: str) -> dt.datetime:
    return dt.datetime.combine(day, dt.time(int(hhmm[:2]), int(hhmm[2:])), tzinfo=IST).astimezone(
        dt.UTC
    )


def _day(text: str, default_year: int) -> dt.date | None:
    """'the 28th September 2026', '4th December, 2023', '29th September'."""
    m = re.search(r"(\d{1,2})\s*(?:st|nd|rd|th)?\s+([A-Za-z]+),?\s*(\d{4})?", text)
    if not m or m.group(2).lower() not in _MONTHS:
        return None
    year = int(m.group(3)) if m.group(3) else default_year
    return dt.date(year, _MONTHS[m.group(2).lower()], int(m.group(1)))


def parse_text(raw: str) -> ParsedBulletin:
    t = normalise(raw)
    if len(t) < 200 or "Bulletin" not in t:
        return ParsedBulletin(status="unreadable", missing=["text"])
    b = ParsedBulletin(status="ok")

    m = re.search(
        r"National Bulletin\s*No\.?\s*(\d+)\s*\(\s*([A-Z]{3})\s*/\s*(\d+)\s*/\s*(\d{4})", t, re.I
    )
    if m:
        b.number = int(m.group(1))
        b.basin = m.group(2).upper()
        b.system_id = f"{b.basin}/{int(m.group(3)):02d}/{m.group(4)}"

    m = re.search(
        r"TIME OF ISSUE\s*:?\s*(\d{4})\s*HOURS IST.{0,40}?"
        r"DATED\s*:?\s*(\d{1,2})\.(\d{1,2})\.(\d{4})",
        t,
        re.I,
    )
    if m:
        issue_day = dt.date(int(m.group(4)), int(m.group(3)), int(m.group(2)))
        b.issued_at = _ist(issue_day, m.group(1))
    year = b.issued_at.astimezone(IST).year if b.issued_at else dt.date.today().year

    m = re.search(
        r"\bSub(?:ject)?\s*:\s*(.{10,400}?)(?=\s(?:The|A|An)\s[A-Z]|\sIndia Meteorological|$)", t
    )
    if m:
        b.subject = m.group(1).strip()
    if b.subject and (n := re.search(r'"([A-Z]{3,})"', b.subject)):
        b.name = n.group(1)

    for row in re.finditer(
        r"(\d{2})\.(\d{2})\.(\d{2})\s*/\s*(\d{4})\s+(\d{1,2}\.\d)\s*/\s*(\d{2,3}\.\d)\s+"
        r"(\d{2,3})\s*-\s*(\d{2,3})\s*(?:kmph)?\s*gusting\s*(?:to)?\s*(\d{2,3})\s*(?:kmph)?\s*"
        rf"({_CATEGORY_RE})",
        t,
        re.I,
    ):
        day = dt.date(2000 + int(row.group(3)), int(row.group(2)), int(row.group(1)))
        b.track.append(
            TrackPoint(
                at=_ist(day, row.group(4)),
                lat=float(row.group(5)),
                lon=float(row.group(6)),
                wind_kmph=(int(row.group(7)), int(row.group(8))),
                gust_kmph=int(row.group(9)),
                category=_canonical(row.group(10)),
            )
        )

    m = re.search(
        r"Latitude\s*([\d.]+)\s*°?\s*N\s*,?\s*(?:and)?\s*Longitude\s*([\d.]+)\s*°?\s*E", t, re.I
    )
    if m:
        b.lat, b.lon = float(m.group(1)), float(m.group(2))
    m = re.search(
        r"(?:centred|centered)\s+at\s+(\d{4})\s*(?:hrs|hours)\s*IST\s*(?:of)?\s*(.{0,40})", t, re.I
    )
    if m and (day := _day(m.group(2), year)):
        b.centre_at = _ist(day, m.group(1))
    if b.track and b.lat is not None and b.centre_at is None:
        b.centre_at = b.track[0].at  # the table's first row is the analysis

    # Category: the analysis row of the table, else what the subject says the
    # system became ("weakened into a Well Marked Low"), else its first mention.
    if b.track and b.track[0].category:
        b.category = b.track[0].category
    elif b.subject:
        became = re.search(
            rf"(?:weakened|intensified|concentrated)\s*in\s*to\s+an?\s+({_CATEGORY_RE})",
            b.subject,
            re.I,
        )
        first = re.search(rf"({_CATEGORY_RE})", b.subject, re.I)
        pick = became or first
        b.category = _canonical(pick.group(1)) if pick else None

    m = re.search(
        r"Fishermen\s+(?:Warning[^:]{0,40}:\s*)?(Fishermen\s+)?(are advised.{10,700}?)"
        r"(?=\(v\)|Impact expected|Next bulletin|$)",
        t,
        re.I,
    )
    if m:
        b.fishermen_warning = ("Fishermen " + m.group(2)).strip(" .") + "."

    # "Next bulletin will be issued at", or in 2023 "the n ext message will be
    # issued at" (the PDF splits words): any "next ... will be issued at".
    m = re.search(
        r"n\s?ext\s+(?:bulletin|message|update)\s+will\s+be\s+issued\s+at\s*(\d{4})\s*hours?\s*IST"
        r"\s*(?:of)?\s*(.{0,40})",
        t,
        re.I,
    )
    if m:
        day = _day(m.group(2), year)
        if day is None and "today" in m.group(2).lower() and b.issued_at:
            day = b.issued_at.astimezone(IST).date()
        if day:
            b.next_issue_at = _ist(day, m.group(1))

    for name in ("number", "system_id", "issued_at", "category"):
        if getattr(b, name) is None:
            b.missing.append(name)
    # A disturbance must have a centre: the override is measured from it.
    if b.category in DISTURBANCES and (b.lat is None or b.centre_at is None):
        b.missing.append("centre")
    if b.missing:
        b.status = "partial"
    return b


def parse_pdf(data: bytes) -> ParsedBulletin:
    """A PDF that cannot even be opened is unreadable, not an exception: the
    caller still has to warn about it."""
    try:
        text = pdf_text(data)
    except Exception:
        return ParsedBulletin(status="unreadable", missing=["pdf"])
    return parse_text(text)


def _canonical(category: str) -> str:
    low = re.sub(r"\s+", " ", category).strip().lower()
    for c in CATEGORIES:
        if c.lower() == low:
            return c
    return category
