#!/usr/bin/env python
"""Render the shore console's satellite layers to static PNGs.

The layers are fixed renders of the COGs in data/cogs (made by
dhruva.geo.generate_cogs), so the deployed app needs no tile server: each COG
is rendered once, in Web Mercator so its corners pin exactly onto the map,
with the same colour scales the console's legend shows (ShoreApp RASTER_STYLE).
Output: frontend/public/rasters/<layer>.png and manifest.json (bounds and the
COG manifest's provenance).

Needs the local TiTiler (docker compose up -d titiler) on :8001.

    python scripts/render_rasters.py
"""

from __future__ import annotations

import json
import math
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "frontend/public/rasters"
TITILER = "http://localhost:8001"
# Must match RASTER_STYLE in frontend/src/shore/ShoreApp.tsx.
STYLE = {"sst": ((18, 33), "thermal"), "chlorophyll": ((0, 5), "algae"), "wave_height": ((0, 8), "blues")}
WIDTH = 1400


def merc_y(lat: float) -> float:
    return math.log(math.tan(math.pi / 4 + math.radians(lat) / 2))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((ROOT / "data/cogs/manifest.json").read_text())
    meta = {}
    for layer, ((lo, hi), cmap) in STYLE.items():
        src = f"file:///data/cogs/{manifest[layer]['file']}"
        info = json.load(urllib.request.urlopen(f"{TITILER}/cog/info?url={urllib.parse.quote(src)}"))
        w, s, e, n = info["bounds"]
        height = round(WIDTH * (merc_y(n) - merc_y(s)) / math.radians(e - w))
        q = urllib.parse.urlencode(
            {"url": src, "dst_crs": "EPSG:3857", "rescale": f"{lo},{hi}", "colormap_name": cmap}
        )
        png = urllib.request.urlopen(f"{TITILER}/cog/bbox/{w},{s},{e},{n}/{WIDTH}x{height}.png?{q}").read()
        (OUT / f"{layer}.png").write_bytes(png)
        meta[layer] = {"image": f"/rasters/{layer}.png", "bounds": [w, s, e, n], **manifest[layer]}
        print(f"{layer}: {WIDTH}x{height}, {len(png) // 1024} KB")
    (OUT / "manifest.json").write_text(json.dumps(meta, indent=2) + "\n")


if __name__ == "__main__":
    main()
