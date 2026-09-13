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

from pathlib import Path
from typing import Any

import yaml

from dhruva.codec.codec import Capsule, saturating_fields
from dhruva.codec.fields import RISK_CLASSES

_STRUCTURE_PATH = Path(__file__).resolve().parents[3] / "data" / "codebook" / "structure.yaml"


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
