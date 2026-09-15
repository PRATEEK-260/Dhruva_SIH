"""Provenance for the Shore Console raster layers.

A COG is only pixels. The console may not colour the sea without saying which
dataset and which hour produced the colour, so generate_cogs writes a manifest
row beside every file and the api serves the manifest. Kept free of rasterio/
rioxarray imports so the api can read it without the raster stack.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

MANIFEST_NAME = "manifest.json"


def cog_dir() -> Path:
    default = Path(__file__).resolve().parents[3] / "data"
    return Path(os.environ.get("DHRUVA_DATA_DIR", str(default))) / "cogs"


def read_manifest(directory: Path | None = None) -> dict[str, dict[str, Any]]:
    path = (directory or cog_dir()) / MANIFEST_NAME
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def write_manifest_entry(layer: str, entry: dict[str, Any], directory: Path | None = None) -> None:
    directory = directory or cog_dir()
    directory.mkdir(parents=True, exist_ok=True)
    manifest = read_manifest(directory)
    manifest[layer] = entry
    (directory / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def available_layers(directory: Path | None = None) -> list[dict[str, Any]]:
    """Manifest rows whose COG is actually on disk. A row without its file is a
    layer that would render blank, so it is not offered."""
    directory = directory or cog_dir()
    return [
        {"layer": layer, **entry}
        for layer, entry in sorted(read_manifest(directory).items())
        if (directory / entry["file"]).is_file()
    ]
