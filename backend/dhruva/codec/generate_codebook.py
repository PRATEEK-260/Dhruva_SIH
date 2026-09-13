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
    _DATA_DIR,
    SLOT_RE,
    VALID_SLOTS,
    entry_key,
    is_reachable,
)

# Reuses codebook.py's own DHRUVA_DATA_DIR-aware path rather than recomputing
# parents[3] a second time — two independent computations of "where is the
# repo root" is exactly the kind of drift that broke the api container (this
# file's copy would have been wrong in the same way, just not on the path that
# happened to crash first).
CODEBOOK = _DATA_DIR / "codebook"
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


def compose(
    band: int,
    family: int,
    modifier: int,
    templates: dict[str, Any],
    notice: str,
) -> str:
    """Join complete sentences: verdict, evidence, clause, notice.

    Never splices fragments into one sentence — that is what keeps composition
    safe in SOV languages, where clause order inside a sentence differs from
    English but sentence order does not.
    """
    parts = [templates["band"][band], templates["evidence"][f"{band}.{family}"]]
    clause = templates["modifier"].get(modifier)
    if clause:
        parts.append(clause)
    parts.append(notice)
    return " ".join(part.strip() for part in parts)


def build_language(language: str) -> dict[str, Any]:
    templates = _load_yaml(CODEBOOK / "templates" / f"{language}.yaml")
    lexicon = _load_yaml(CODEBOOK / "lexicons" / f"{language}.yaml")
    notice = lexicon["notice"]

    wanted = set(reachable_keys())
    wanted_pairs = {(b, f) for b in range(4) for f in range(8) if is_reachable(b, f, 0)}
    wanted_modifiers = {
        m for b in range(4) for f in range(8) for m in range(8) if is_reachable(b, f, m)
    }

    have_pairs = {tuple(int(x) for x in k.split(".")) for k in templates["evidence"]}
    if have_pairs != wanted_pairs:
        raise ValueError(
            f"{language}: evidence keys do not match the reachable band.family set. "
            f"missing={sorted(wanted_pairs - have_pairs)} extra={sorted(have_pairs - wanted_pairs)}"
        )
    if set(templates["band"]) != set(range(4)):
        raise ValueError(f"{language}: needs exactly four band openers")
    missing_mods = (wanted_modifiers - {0}) - set(templates["modifier"])
    if missing_mods:
        raise ValueError(f"{language}: no clause for modifier(s) {sorted(missing_mods)}")

    for section in ("band", "evidence", "modifier"):
        for key, text in templates[section].items():
            _check_slots(language, f"{section}[{key}]", text)
            _check_digits(language, f"{section}[{key}]", text)
    _check_digits(language, "notice", notice)

    entries: dict[str, str] = {}
    for band in range(4):
        generic = compose(band, 0, 0, templates, notice)
        for family in range(8):
            for modifier in range(8):
                key = entry_key(band, family, modifier)
                if is_reachable(band, family, modifier):
                    entries[key] = compose(band, family, modifier, templates, notice)
                else:
                    # Unreachable: speak the band's generic sentence rather than
                    # inventing one for a combination the engine cannot produce.
                    entries[key] = generic

    return {
        "version": 1,
        "language": language,
        "notice": notice,
        "reachable": sorted(wanted),
        "entries": dict(sorted(entries.items())),
        # Embedded rather than left as a second file: the TypeScript port needs
        # exactly one artifact per language to import statically, and the
        # Python runtime path (codebook.render) gets to stop opening a second
        # file per render call. The generator itself still reads the source
        # YAML directly (_load_yaml above) — this is only about what ships.
        "lexicon": lexicon,
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
