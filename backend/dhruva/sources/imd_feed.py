"""Fetch IMD's National Bulletins as they are published.

IMD has no API. RSMC New Delhi lists every National Bulletin, newest first, on
its archive page, each a PDF at a stable path. This reads that listing,
downloads any bulletin not seen before, keeps the PDF and its SHA-256, parses
it (sources/imd_parser.py) and records the result in data/imd/feed.json along
with when the listing was last checked. That time is what lets an answer say
"No active IMD cyclone bulletin as of <time>" rather than "no danger".

Run it on a schedule (every 30 minutes; deploy/render/start.sh loops it):

    python -m dhruva.sources.imd_feed

This is a public web page read and attributed, not a feed IMD offers; the
source URL travels with every bulletin.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path
from typing import Any
from urllib.parse import quote, urljoin

import httpx

from dhruva.sources.imd_parser import parse_pdf

BASE = "https://rsmcnewdelhi.imd.gov.in/"
LISTING = BASE + "archive-information.php?internal_menu=MQ%3D%3D&menu_id=NA%3D%3D"
ISSUER = "IMD, RSMC Tropical Cyclones New Delhi"
# Each listing shows the newest 30; a bulletin comes every 3-6 hours while a
# system is active, so the newest few are all that can be current.
FETCH_NEWEST = 4
_UA = {"User-Agent": "DHRUVA/0.1 (SIH 2025 PS 26176; marine advisory research prototype)"}

_DATA = Path(os.environ.get("DHRUVA_DATA_DIR", "data"))
FEED_PATH = _DATA / "imd" / "feed.json"
PDF_DIR = _DATA / "imd" / "national"

_ROW = re.compile(
    r"<td>\s*(National Bulletin[^<]*)</td>\s*<td>\s*([^<]*)</td>\s*"
    r"<td>\s*<a href=\"([^\"]+\.pdf)\"",
    re.I,
)


def listing_rows(page: str) -> list[dict[str, str]]:
    """(title, listed issue time, absolute URL) for each row, newest first."""
    rows = []
    for title, when, href in _ROW.findall(page):
        url = urljoin(BASE, quote(html.unescape(href), safe="/%:"))
        # The page is scraped, so its links are untrusted: only a PDF on IMD's
        # own host is fetched or shown. urljoin passes "javascript:..." or
        # another host straight through, and the phone renders this as a link.
        if not url.startswith(BASE + "uploads/"):
            continue
        rows.append({"title": title.strip(), "listed_at": when.strip(), "url": url})
    return rows


def entry_for(pdf: bytes, url: str, local: Path, fetched_at: dt.datetime) -> dict[str, Any]:
    """One stored bulletin: what the parser read, and where it came from."""
    parsed = parse_pdf(pdf)
    return {
        **parsed.as_dict(),
        "issuer": ISSUER,
        "source_url": url,
        "local_copy": str(local),
        "sha256": hashlib.sha256(pdf).hexdigest(),
        "fetched_at": fetched_at.isoformat(),
    }


def load_feed(path: Path = FEED_PATH) -> dict[str, Any]:
    if not path.exists():
        return {"checked_at": None, "error": None, "bulletins": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def refresh(
    client: httpx.Client, path: Path = FEED_PATH, pdf_dir: Path = PDF_DIR
) -> dict[str, Any]:
    """Check the listing once and store anything new. A failed check is
    recorded with its error and the previous bulletins are kept: they still
    expire by their own validity, so a dead feed cannot keep a stale warning
    alive, and checked_at stops advancing so the answer says how old it is."""
    feed = load_feed(path)
    now = dt.datetime.now(dt.UTC)
    try:
        r = client.get(LISTING, headers=_UA, timeout=30, follow_redirects=True)
        r.raise_for_status()
        rows = listing_rows(r.text)
        if not rows:
            raise ValueError(
                "listing had no National Bulletin rows; the page layout may have changed"
            )
        pdf_dir.mkdir(parents=True, exist_ok=True)
        known = {b["source_url"] for b in feed["bulletins"].values()}
        for row in rows[:FETCH_NEWEST]:
            if row["url"] in known:
                continue
            pdf = client.get(row["url"], headers=_UA, timeout=60, follow_redirects=True)
            pdf.raise_for_status()
            local = pdf_dir / Path(row["url"]).name.replace("%20", "_")
            local.write_bytes(pdf.content)
            entry = entry_for(pdf.content, row["url"], local, now)
            entry["listed_title"] = row["title"]
            feed["bulletins"][hashlib.sha256(row["url"].encode()).hexdigest()[:16]] = entry
        feed["checked_at"], feed["error"] = now.isoformat(), None
    except Exception as exc:
        feed["error"] = f"{type(exc).__name__}: {exc}"
        feed["error_at"] = now.isoformat()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(feed, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)  # readers never see half a file
    return feed


def main() -> int:
    with httpx.Client() as client:
        feed = refresh(client)
    ok = feed.get("error") is None
    newest = sorted(feed["bulletins"].values(), key=lambda b: b.get("issued_at") or "")[-3:]
    for b in newest:
        print(
            f"{b.get('issued_at')}  No. {b.get('number')} {b.get('system_id')}  "
            f"{b.get('category')}  {b['status']}  centre {b.get('lat')},{b.get('lon')}"
        )
    print(f"checked {feed['checked_at']}" if ok else f"FAILED {feed['error']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
