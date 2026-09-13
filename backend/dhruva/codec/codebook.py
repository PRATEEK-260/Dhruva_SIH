"""The reason codebook — index arithmetic and degradation.

The capsule spends 8 bits on `reason_code`. Those 8 bits are the entire
explanation a crew hears when the phone has no network, so they are structured
rather than enumerated:

    bits 7-6  band      mirrors risk_class (offset 57) exactly
    bits 5-3  family    deciding-rule family
    bits 2-0  modifier  secondary clause

Band mirroring is the safety property. The capsule now carries the verdict twice,
68 bits apart, and `reason_code >> 6 == risk_class` is a one-comparison coherence
check. Note the risk_class encoding is NOT monotonic in severity — no_go is 0b10
and flipping the high bit yields 0b00, safe — so banding buys nothing on its own.
The protection is entirely the cross-check between the two copies.

Field table and rationale: docs/CAPSULE_SPEC.md and
docs/superpowers/specs/2026-09-13-reason-codebook-design.md.
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

from dhruva.codec.codec import Capsule, saturating_fields
from dhruva.codec.fields import RISK_CLASSES

# parents[3] from this file's local-checkout depth (backend/dhruva/codec/
# codebook.py, four levels below the repo root) is only correct for that exact
# layout. docker-compose.yml's api service builds from a `backend/` context and
# bind-mounts ./backend:/app, so inside the container this file lives at
# /app/dhruva/codec/codebook.py — two levels below /app, not four below the
# repo root — and data/ was never part of that build context at all. Found by
# the api container crash-looping on this exact FileNotFoundError once the
# graph deps were fixed. DHRUVA_DATA_DIR lets the container set the real path
# (data/ bind-mounted separately) rather than this module guessing a depth
# that only ever matches one deployment shape.
_DATA_DIR = Path(os.environ.get("DHRUVA_DATA_DIR", str(Path(__file__).resolve().parents[3] / "data")))
_STRUCTURE_PATH = _DATA_DIR / "codebook" / "structure.yaml"


def _load() -> dict[str, Any]:
    with _STRUCTURE_PATH.open(encoding="utf-8") as fh:
        return yaml.safe_load(fh)


_S = _load()

VERSION: int = _S["version"]
BANDS: dict[int, str] = _S["bands"]
FAMILIES: dict[int, str] = _S["families"]
MODIFIERS: dict[int, str] = _S["modifiers"]
RULE_FAMILY: dict[str, int] = _S["rule_family"]
SATURATED_BRIDGE: dict[str, str] = _S["saturated_bridge"]
MODIFIER_PRIORITY: list[str] = _S["modifier_priority"]

_REACHABLE_FAMILIES: dict[int, list[int]] = _S["reachable_families"]
_MODIFIER_CONSTRAINTS: dict[str, dict[str, list[int]]] = _S["modifier_constraints"]
_TRIGGERS: dict[str, int] = _S["narration_triggers"]

MODIFIER_ID: dict[str, int] = {name: value for value, name in MODIFIERS.items()}

# The band value IS the index into RISK_CLASSES, which is what makes the mirror
# exact rather than merely parallel.
_BAND_OF: dict[str, int] = {name: i for i, name in enumerate(RISK_CLASSES)}

# Which decoded attribute each family's number comes from. Used to decide whether
# the saturated modifier applies to THIS family rather than to any railed field.
_FAMILY_WIRE_FIELD: dict[int, str] = {1: "wave_hs", 2: "wind_kt"}


def split_reason(code: int) -> tuple[int, int, int]:
    """Take the byte apart. Pure, and the inverse of the shift in reason_index."""
    if not 0 <= code <= 255:
        raise ValueError(f"reason_code must fit one byte, got {code}")
    return (code >> 6) & 0b11, (code >> 3) & 0b111, code & 0b111


def join_reason(band: int, family: int, modifier: int) -> int:
    """Assemble the byte. Raises rather than truncating a caller's mistake."""
    for name, value, top in (("band", band, 3), ("family", family, 7), ("modifier", modifier, 7)):
        if not 0 <= value <= top:
            raise ValueError(f"{name} out of range: {value}")
    return (band << 6) | (family << 3) | modifier


def is_reachable(band: int, family: int, modifier: int) -> bool:
    """Can the risk engine actually produce this combination?

    Absolute overrides return early from assess(), so cyclone, lightning and
    tsunami exist only in the no_go band; DATA-U0 yields UNKNOWN and nothing
    else. Unreachable combinations still get codebook entries (the gate requires
    exactly 256) but decode as degraded.
    """
    if family not in _REACHABLE_FAMILIES.get(band, []):
        return False
    constraint = _MODIFIER_CONSTRAINTS.get(MODIFIERS[modifier])
    if constraint is None:
        return False
    if "bands" in constraint and band not in constraint["bands"]:
        return False
    return not ("families" in constraint and family not in constraint["families"])


def _modifier_applies(name: str, band: int, family: int, capsule: Capsule | None) -> bool:
    """Whether this clause is true of this advisory.

    Every branch reads a capsule field or a declared trigger. Nothing here
    invents a number.
    """
    if name == "none":
        return True
    if name == "provisional":
        from dhruva.risk.thresholds import PROVISIONAL

        return bool(PROVISIONAL)
    if name == "return_now":
        return band == _BAND_OF["no_go"]
    if capsule is None:
        return False
    if name == "saturated":
        wire = _FAMILY_WIRE_FIELD.get(family)
        return wire is not None and wire in saturating_fields(capsule)
    if name == "pfz_outranked":
        return capsule.pfz_dist_nm > 0 and band >= _BAND_OF["caution"]
    if name == "pfz_reachable":
        return capsule.pfz_dist_nm > 0 and capsule.pfz_conf >= _TRIGGERS["pfz_min_confidence"]
    if name == "boundary_near":
        return capsule.bnd_type != "none" and capsule.bnd_dist_nm <= _TRIGGERS["boundary_near_nm"]
    return False


def _modifier_for(band: int, family: int, capsule: Capsule | None) -> int:
    """Pick one clause. Only one fits in the byte, so priority decides.

    `saturated` outranks `return_now` deliberately: a no_go sentence already says
    do not go out, but quoting a railed 7.75 m reading as exact when the sea is
    9 m is the specific lie docs/CAPSULE_SPEC.md exists to prevent.
    """
    for name in MODIFIER_PRIORITY:
        modifier = MODIFIER_ID[name]
        if not is_reachable(band, family, modifier):
            continue
        if _modifier_applies(name, band, family, capsule):
            return modifier
    return MODIFIER_ID["none"]


def reason_index(assessment: Any, capsule: Capsule | None = None) -> int:
    """Compute the codebook index from the verdict and the rule that set it.

    Never a lookup: the decoder recovers the same three parts with shifts, so the
    two sides cannot hold drifting tables.
    """
    band = _BAND_OF[str(assessment.risk_class)]
    rule = assessment.deciding_rule
    family = RULE_FAMILY.get(rule.rule_id, 0) if rule is not None else 0
    if family not in _REACHABLE_FAMILIES.get(band, []):
        # The rule and the verdict disagree about what is possible. Say less
        # rather than saying something the engine cannot justify.
        family = 0
    modifier = _modifier_for(band, family, capsule)
    return join_reason(band, family, modifier)


# --------------------------------------------------------------- rendering ----
#
# Slots bind to decoded Capsule attributes, NEVER to wire field names. A slot is
# the only way a number reaches a sentence, which is what makes the codebook
# firewall-clean by construction rather than by inspection.

# Rendered as a number, straight off the capsule.
DIRECT_SLOTS: frozenset[str] = frozenset(
    {
        "wave_hs_m",
        "wind_kt",
        "curr_kt",
        "sst_c",
        "pfz_dist_nm",
        "bnd_dist_nm",
        "bnd_eta_min",
        "valid_hours",
    }
)

# The only unit conversions CLAUDE.md permits. Declared, not open-ended, and
# using the exact same factors as evidence/firewall.py's DECLARED_CONVERSIONS —
# two independently-declared tables for the same physical conversion is exactly
# the kind of drift that lets the firewall reject a codebook sentence for using
# a "wrong" number that is actually just a different rounding of the same unit.
# test_codebook_render.py::test_conversion_factors_match_the_firewall pins this.
CONVERTED_SLOTS: dict[str, tuple[str, float]] = {
    "wave_hs_ft": ("wave_hs_m", 3.280839895),
    "wind_kmh": ("wind_kt", 1.852),
}

# Rendered as a WORD via the per-language lexicon, so they carry no digits.
# Named _name so {wind_dir_deg} (the number) can never be confused with
# {wind_dir_name} ("north-northwest"). A bearing spoken as a number is useless.
LEXICON_SLOTS: dict[str, tuple[str, str]] = {
    "wind_dir_name": ("wind_dir_deg", "compass"),
    "curr_dir_name": ("curr_dir_deg", "compass"),
    "pfz_bearing_name": ("pfz_bearing_deg", "compass"),
    "bnd_type_name": ("bnd_type", "bnd_type"),
    "chl_class_name": ("chl_class", "chl_class"),
    "msg_type_name": ("msg_type", "msg_type"),
}

VALID_SLOTS: frozenset[str] = frozenset(DIRECT_SLOTS | set(CONVERTED_SLOTS) | set(LEXICON_SLOTS))

SLOT_RE = re.compile(r"\{([a-z_]+)\}")


def entry_key(band: int, family: int, modifier: int) -> str:
    return f"b{band}f{family}m{modifier}"


def _number(value: float) -> str:
    """Two decimals, trimmed. Matches evidence/firewall.py so the online card and
    the offline card agree on screen, and so the validator recognises the token."""
    return f"{round(float(value), 2):g}"


def _compass(degrees: float, lexicon: dict[str, Any]) -> str:
    """The lexicon `fill` receives always comes from a JSON build artifact now
    (render() reads it out of load_codebook()[...]["lexicon"]), and JSON object
    keys are always strings — the YAML source has integer keys, but that
    distinction does not survive the JSON round-trip generate_codebook.py
    performs. str(index), not index, is the correct lookup on the runtime
    path."""
    index = round(float(degrees) / 22.5) % 16
    return lexicon["compass"][str(index)]


def fill(template: str, capsule: Capsule, lexicon: dict[str, Any]) -> str:
    """Substitute slots. Raises on an unknown slot rather than leaving it visible."""

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in DIRECT_SLOTS:
            return _number(getattr(capsule, name))
        if name in CONVERTED_SLOTS:
            source, factor = CONVERTED_SLOTS[name]
            return _number(getattr(capsule, source) * factor)
        if name in LEXICON_SLOTS:
            source, table = LEXICON_SLOTS[name]
            raw = getattr(capsule, source)
            return _compass(raw, lexicon) if table == "compass" else lexicon[table][raw]
        raise KeyError(f"unknown slot {{{name}}}")

    return SLOT_RE.sub(replace, template)


# ------------------------------------------------------------- degradation ----

_BUILD_DIR = _STRUCTURE_PATH.parent / "build"
_CODEBOOK_CACHE: dict[str, dict[str, Any]] = {}


def load_codebook(language: str) -> dict[str, Any]:
    """Read a built codebook, cached. Read once at first use, never per decode."""
    if language not in _CODEBOOK_CACHE:
        path = _BUILD_DIR / f"{language}.json"
        if not path.exists():
            raise FileNotFoundError(
                f"no codebook for {language!r}; run python -m dhruva.codec.generate_codebook"
            )
        with path.open(encoding="utf-8") as fh:
            _CODEBOOK_CACHE[language] = json.load(fh)
    return _CODEBOOK_CACHE[language]


_LEXICON_CACHE: dict[str, dict[str, Any]] = {}


def load_lexicon(language: str) -> dict[str, Any]:
    """Compass points and enum labels. Words only — nothing here carries a digit."""
    if language not in _LEXICON_CACHE:
        path = _STRUCTURE_PATH.parent / "lexicons" / f"{language}.yaml"
        if not path.exists():
            raise FileNotFoundError(f"no lexicon for {language!r}")
        with path.open(encoding="utf-8") as fh:
            _LEXICON_CACHE[language] = yaml.safe_load(fh)
    return _LEXICON_CACHE[language]


@dataclass(frozen=True, slots=True)
class ReasonRender:
    """What the phone should say, and whether it had to fall back to say it."""

    band: int
    family: int
    modifier: int
    degraded: bool
    text: str


def _severity_of_band(band: int) -> int:
    """Reuse the risk engine's own ordering rather than keeping a second copy."""
    from dhruva.graph.state import RiskClass
    from dhruva.risk.rules import _SEVERITY

    return _SEVERITY[RiskClass(RISK_CLASSES[band])]


def decode_reason(code: int, risk_class: int, language: str = "en") -> ReasonRender:
    """Expand the byte, cross-checking it against the capsule's other copy of the
    verdict.

    Three cases, in the order they are tested:

    1. Coherent and reachable — render the authored entry.
    2. The band disagrees with risk_class — take the MORE SEVERE of the two and
       render that band's generic entry. Family and modifier are discarded: if
       the band bits are corrupt the rest may be too.
    3. Coherent but unreachable — render the band's generic entry.

    Taking the worse band rather than trusting either copy follows the rule the
    risk engine already states: answering "safe" when you do not know is worse
    than answering nothing.
    """
    band, family, modifier = split_reason(code)
    entries = load_codebook(language)["entries"]

    degraded = False
    if band != risk_class:
        if not 0 <= risk_class <= 3:
            raise ValueError(f"risk_class must fit two bits, got {risk_class}")
        band = band if _severity_of_band(band) >= _severity_of_band(risk_class) else risk_class
        family, modifier = 0, 0
        degraded = True
    elif not is_reachable(band, family, modifier):
        family, modifier = 0, 0
        degraded = True

    key = entry_key(band, family, modifier)
    return ReasonRender(band, family, modifier, degraded, entries[key])


def render(capsule: Capsule, language: str = "en") -> str:
    """The whole offline path: capsule in, spoken sentence out. Pure apart from
    the one cached codebook read.

    Reads the lexicon from the SAME build artifact as the entries (embedded by
    generate_codebook.py), not a second load_lexicon() file open — one artifact
    per language is also what the TypeScript port imports, so the two runtimes
    read identically-shaped data."""
    risk_class = _BAND_OF[capsule.risk_class]
    chosen = decode_reason(capsule.reason_code, risk_class, language)
    return fill(chosen.text, capsule, load_codebook(language)["lexicon"])
