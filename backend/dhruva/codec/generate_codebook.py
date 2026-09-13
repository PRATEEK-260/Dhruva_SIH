"""Generate data/codebook/build/<lang>.json from one structure and per-language
templates and lexicons.

All 256 keys are emitted because Gate 4 requires exactly 256 renderable entries
(IMPLEMENTATION.md:138). Only the reachable combinations are authored; the rest
take their band's generic text and are marked unreachable, so a phone that
decodes an impossible combination still speaks something true rather than
nothing.

Run: python -m dhruva.codec.generate_codebook
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml

from dhruva.codec.codebook import (
    SLOT_RE,
    VALID_SLOTS,
    entry_key,
    is_reachable,
)

ROOT = Path(__file__).resolve().parents[3]
CODEBOOK = ROOT / "data" / "codebook"
BUILD = CODEBOOK / "build"

LANGUAGES = ("en", "ta", "te", "ml", "kn", "mr", "kok", "gu", "or", "bn", "hi", "ur")


def reachable_keys() -> list[str]:
    """Every combination the risk engine can actually produce, in index order."""
    return [
        entry_key(b, f, m)
        for b in range(4)
        for f in range(8)
        for m in range(8)
        if is_reachable(b, f, m)
    ]


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _check_slots(language: str, key: str, text: str) -> None:
    for name in SLOT_RE.findall(text):
        if name not in VALID_SLOTS:
            raise ValueError(
                f"{language}:{key} uses unknown slot {{{name}}}. "
                f"Slots bind to decoded Capsule attributes, not wire field names."
            )


def _check_digits(language: str, key: str, text: str) -> None:
    stripped = SLOT_RE.sub("", text)
    bad = [ch for ch in stripped if ch.isdigit()]
    if bad:
        raise ValueError(
            f"{language}:{key} contains literal digit(s) {bad!r}. "
            f"Every number must come from a slot, or it is a number with no evidence."
        )


def build_language(language: str) -> dict[str, Any]:
    templates = _load_yaml(CODEBOOK / "templates" / f"{language}.yaml")
    lexicon = _load_yaml(CODEBOOK / "lexicons" / f"{language}.yaml")
    notice = lexicon["notice"]

    authored = {k: v for k, v in templates.items() if k.startswith("b") and k[1:2].isdigit()}
    wanted = set(reachable_keys())

    extra = set(authored) - wanted
    if extra:
        raise ValueError(f"{language}: authored keys that are not reachable: {sorted(extra)}")
    missing = wanted - set(authored)
    if missing:
        raise ValueError(f"{language}: reachable keys with no template: {sorted(missing)}")

    for key, text in authored.items():
        _check_slots(language, key, text)
        _check_digits(language, key, text)
    _check_digits(language, "notice", notice)

    entries: dict[str, str] = {}
    for band in range(4):
        generic = f"{authored[entry_key(band, 0, 0)].rstrip()} {notice}"
        for family in range(8):
            for modifier in range(8):
                key = entry_key(band, family, modifier)
                if key in authored:
                    entries[key] = f"{authored[key].rstrip()} {notice}"
                else:
                    # Unreachable: degrade to the band's generic text rather than
                    # inventing a sentence for a combination that cannot happen.
                    entries[key] = generic

    return {
        "version": 1,
        "language": language,
        "notice": notice,
        "reachable": sorted(wanted),
        "entries": dict(sorted(entries.items())),
    }


def main() -> None:
    BUILD.mkdir(parents=True, exist_ok=True)
    built = 0
    for language in LANGUAGES:
        if not (CODEBOOK / "templates" / f"{language}.yaml").exists():
            continue
        doc = build_language(language)
        # sort_keys and a trailing newline keep the output byte-stable, which is
        # what makes the determinism test meaningful.
        (BUILD / f"{language}.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        built += 1
    print(f"built {built} language(s), {len(reachable_keys())} reachable of 256")


if __name__ == "__main__":
    main()
