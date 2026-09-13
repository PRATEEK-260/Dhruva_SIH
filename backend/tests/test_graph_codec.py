"""Node 9 — the graph's own capsule assembly.

CLAUDE.md: the LLM never emits a number, and every quantiser clamps. Node 9 sits
downstream of both rules, so these tests check the two places a graph-side bug
could reintroduce the same failure shape without any LLM involved at all: a
reason_code whose band disagrees with risk_class, or a boundary/ETA clause
rendered from data the graph never actually computed.
"""

from __future__ import annotations

import datetime as dt

import pytest

from dhruva.codec.codebook import split_reason
from dhruva.codec.codec import decode, from_base32
from dhruva.graph.build import _issue_slot, codec
from dhruva.graph.state import BoatClass, initial_state
from dhruva.sources.base import Observation
from dhruva.sources.registry import Variable

NOW = dt.datetime(2026, 9, 13, 10, 0, tzinfo=dt.UTC)  # a Sunday


def _obs(var: Variable, value: float, unit: str) -> Observation:
    return Observation(
        variable=var,
        value=value,
        unit=unit,
        dataset_id="d",
        upstream_dataset_id="u",
        valid_time=NOW,
        cell_lat=11.05,
        cell_lon=79.95,
        requested_lat=11.05,
        requested_lon=79.95,
        grid_resolution_deg=0.083,
        fetched_at=NOW,
    )


def _state(wave: float, wind: float, boat: BoatClass = BoatClass.FRP_UNDER_12M):
    s = initial_state("can I go out?", 11.05, 79.95, when=NOW, boat_class=boat)
    s["observations"] = [
        _obs(Variable.WAVE_HEIGHT, wave, "m"),
        _obs(Variable.WIND_SPEED, wind, "kt"),
        _obs(Variable.WIND_DIRECTION, 90.0, "deg"),
        _obs(Variable.CURRENT_SPEED, 1.2, "kt"),
        _obs(Variable.CURRENT_DIRECTION, 180.0, "deg"),
        _obs(Variable.SST, 28.5, "degC"),
    ]
    return s


class TestNodeNineBandCoherence:
    """The whole safety property of the structured reason index is that its
    band matches risk_class. If node 9 ever got that wrong, no downstream test
    would catch it — decode_reason's mismatch path would just quietly degrade
    it, which is correct behaviour for a DAMAGED capsule but would be masking a
    real bug if the capsule was never damaged in the first place."""

    def test_a_calm_sea_produces_a_safe_band(self):
        out = codec(_state(wave=0.5, wind=8.0))
        band, _family, _modifier = split_reason(out["reason_code"])
        assert band == 0

    def test_a_rough_sea_produces_a_no_go_band(self):
        out = codec(_state(wave=9.0, wind=50.0))
        band, family, _modifier = split_reason(out["reason_code"])
        assert band == 2
        assert family == 1  # wave is the deciding rule at 9 m

    def test_missing_readings_produce_the_unknown_band(self):
        s = initial_state("can I go out?", 11.05, 79.95, when=NOW)
        s["observations"] = []
        out = codec(s)
        band, family, _modifier = split_reason(out["reason_code"])
        assert band == 3
        assert family == 6  # DATA-U0


class TestNodeNineCapsuleBits:
    def test_capsule_bits_round_trips_the_real_observations(self):
        out = codec(_state(wave=2.75, wind=22.0))
        capsule = decode(from_base32(out["capsule_bits"]))
        assert capsule.wave_hs_m == pytest.approx(2.75)
        assert capsule.wind_kt == 22
        assert capsule.reason_code == out["reason_code"]

    def test_evidence_hash_is_wired_from_the_same_observations(self):
        """docs/CAPSULE_SPEC.md: evidence_hash is 'truncated SHA-256 of the
        evidence bundle, for audit' — not a placeholder zero. It must match
        what build_bundle() computes for the SAME observations, so the shore
        console's evidence and the capsule's own claim about it agree."""
        from dhruva.evidence.schema import build_bundle
        from dhruva.risk.rules import assess

        state = _state(wave=2.75, wind=22.0)
        out = codec(state)
        capsule = decode(from_base32(out["capsule_bits"]))

        expected = build_bundle(state["observations"], assess(state)).capsule_evidence_hash
        assert capsule.evidence_hash == expected
        assert capsule.evidence_hash != 0

    def test_capsule_bits_is_qr_alphanumeric_safe(self):
        text = codec(_state(wave=1.0, wind=5.0))["capsule_bits"]
        assert set(text) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")


class TestNodeNineDoesNotFabricateBoundaryOrPfz:
    """No PFZ node runs in this graph, and boundary ETA needs drift projection
    that is not built. A "0 minutes to the boundary" would read as real data
    while meaning nothing — the same shape of lie the numeric firewall exists
    to stop, even though it would not come from the LLM."""

    def test_no_boundary_clause_without_a_real_eta(self):
        s = _state(wave=1.0, wind=5.0)
        s["boundaries"] = [
            {"name": "IMBL", "line_type": "imbl", "distance_nm": 3.0, "indicative": True}
        ]
        out = codec(s)
        capsule = decode(from_base32(out["capsule_bits"]))
        assert capsule.bnd_type == "none"
        assert capsule.bnd_dist_nm == 0

    def test_no_pfz_clause_without_a_pfz_node(self):
        out = codec(_state(wave=1.0, wind=5.0))
        capsule = decode(from_base32(out["capsule_bits"]))
        assert capsule.pfz_dist_nm == 0
        assert capsule.pfz_conf == 0


class TestIssueSlot:
    """15-minute resolution, wraps weekly at Monday 00:00 UTC."""

    def test_monday_midnight_is_slot_zero(self):
        monday = dt.datetime(2026, 9, 14, 0, 0, tzinfo=dt.UTC)
        assert _issue_slot(monday) == 0

    def test_one_week_later_wraps_back_to_the_same_slot(self):
        monday = dt.datetime(2026, 9, 14, 6, 30, tzinfo=dt.UTC)
        next_monday = monday + dt.timedelta(days=7)
        assert _issue_slot(monday) == _issue_slot(next_monday)

    def test_fits_the_ten_bit_field(self):
        assert 0 <= _issue_slot(NOW) <= 671

    def test_rejects_a_naive_datetime(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            _issue_slot(dt.datetime(2026, 9, 13, 10, 0))
