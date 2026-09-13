"""The structured reason index.

The 8-bit reason_code decomposes into band / family / modifier. These tests exist
to hold two properties: the band always mirrors risk_class, and an index can
never claim a combination the risk engine cannot produce.
"""

from __future__ import annotations

import pytest

from dhruva.codec.codebook import (
    SATURATED_BRIDGE,
    is_reachable,
    reason_index,
    split_reason,
)
from dhruva.graph.state import RiskClass
from dhruva.risk.rules import FiredRule, RiskAssessment

_BAND = {
    RiskClass.SAFE: 0,
    RiskClass.CAUTION: 1,
    RiskClass.NO_GO: 2,
    RiskClass.UNKNOWN: 3,
}


def _assessment(rule_id: str, verdict: RiskClass) -> RiskAssessment:
    return RiskAssessment(verdict, [FiredRule(rule_id, verdict, None, None, None, "", "")])


def test_band_always_equals_the_top_two_bits_for_every_index() -> None:
    for code in range(256):
        band, _family, _modifier = split_reason(code)
        assert band == code >> 6


def test_split_rejects_a_code_outside_one_byte() -> None:
    for bad in (-1, 256, 1000):
        with pytest.raises(ValueError):
            split_reason(bad)


@pytest.mark.parametrize(
    "rule_id,verdict,family",
    [
        ("WAVE-S1", RiskClass.SAFE, 1),
        ("WAVE-C2", RiskClass.CAUTION, 1),
        ("WAVE-N3", RiskClass.NO_GO, 1),
        ("WIND-S1", RiskClass.SAFE, 2),
        ("WIND-C2", RiskClass.CAUTION, 2),
        ("WIND-N3", RiskClass.NO_GO, 2),
        ("CYCLONE-A1", RiskClass.NO_GO, 3),
        ("LIGHTNING-A2", RiskClass.NO_GO, 4),
        ("TSUNAMI-A3", RiskClass.NO_GO, 5),
        ("DATA-U0", RiskClass.UNKNOWN, 6),
    ],
)
def test_index_band_and_family_match_the_deciding_rule(
    rule_id: str, verdict: RiskClass, family: int
) -> None:
    code = reason_index(_assessment(rule_id, verdict))
    band, fam, _modifier = split_reason(code)
    assert band == _BAND[verdict]
    assert fam == family


def test_every_index_reason_index_produces_is_reachable() -> None:
    """reason_index must never emit a combination the decoder will reject."""
    for rule_id, verdict in [
        ("WAVE-S1", RiskClass.SAFE),
        ("WIND-C2", RiskClass.CAUTION),
        ("CYCLONE-A1", RiskClass.NO_GO),
        ("DATA-U0", RiskClass.UNKNOWN),
    ]:
        code = reason_index(_assessment(rule_id, verdict))
        assert is_reachable(*split_reason(code))


def test_overrides_are_unreachable_outside_the_no_go_band() -> None:
    assert not is_reachable(0, 5, 0)  # tsunami in the safe band
    assert not is_reachable(1, 3, 0)  # cyclone in the caution band
    assert not is_reachable(1, 4, 0)  # lightning in the caution band
    assert is_reachable(2, 5, 0)
    assert is_reachable(2, 3, 0)


def test_data_missing_only_in_the_unknown_band() -> None:
    assert is_reachable(3, 6, 0)
    assert not is_reachable(0, 6, 0)
    assert not is_reachable(1, 6, 0)
    assert not is_reachable(2, 6, 0)


def test_return_now_is_no_go_only() -> None:
    assert is_reachable(2, 0, 5)
    assert not is_reachable(0, 0, 5)
    assert not is_reachable(1, 0, 5)


def test_saturated_only_applies_to_families_that_name_a_railable_field() -> None:
    assert is_reachable(2, 1, 1)  # wave, saturated
    assert is_reachable(1, 2, 1)  # wind, saturated
    assert not is_reachable(2, 3, 1)  # cyclone has no railable capsule field


def test_reserved_slots_are_never_reachable() -> None:
    assert not is_reachable(0, 7, 0)
    assert not is_reachable(2, 1, 7)


def test_saturated_bridge_covers_every_wire_name_saturating_fields_can_return() -> None:
    """Wire names (wave_hs, sst) differ from decoded attributes (wave_hs_m,
    sst_c). An unmapped name would silently disable the saturated modifier, so a
    9 m sea would be spoken as an exact 7.75 m."""
    from dhruva.codec.codec import Capsule, saturating_fields

    railed = Capsule(
        wave_hs_m=99.0,
        wind_kt=999,
        curr_kt=99.0,
        sst_c=99.0,
        pfz_dist_nm=999,
        bnd_dist_nm=999,
        bnd_eta_min=9999,
    )
    hit = saturating_fields(railed)
    assert hit, "the fixture should rail every saturable field"
    for wire_name in hit:
        assert wire_name in SATURATED_BRIDGE, f"{wire_name} missing from the bridge"
        assert hasattr(railed, SATURATED_BRIDGE[wire_name])
