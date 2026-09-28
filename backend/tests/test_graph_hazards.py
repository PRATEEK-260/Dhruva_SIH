"""Absolute overrides reach the graph.

CLAUDE.md: cyclone within 300 km, lightning within 50 km, any tsunami alert →
NO-GO regardless of boat class or sea state. assess() has had those rules since
phase 3, but the graph called it with the sea state alone, so no run could ever
fire them. The hazard inputs now travel on the state: a feed (IMD cyclone
bulletins, lightning) writes them there, and risk, evidence and codec all read
the same values because all three call assess(state).
"""

from __future__ import annotations

import datetime as dt

from dhruva.codec.codec import decode, from_base32
from dhruva.graph.build import codec, evidence, risk
from dhruva.graph.state import RiskClass, initial_state
from dhruva.sources.base import Observation
from dhruva.sources.registry import Variable

NOW = dt.datetime(2026, 9, 28, 3, 0, tzinfo=dt.UTC)


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


def _calm(**hazards):
    s = initial_state("can I go out?", 11.05, 79.95, when=NOW, **hazards)
    s["observations"] = [
        _obs(Variable.WAVE_HEIGHT, 0.3, "m"),
        _obs(Variable.WIND_SPEED, 6.0, "kt"),
        _obs(Variable.WIND_DIRECTION, 90.0, "deg"),
    ]
    return s


class TestCycloneOnTheState:
    def test_a_cyclone_inside_the_radius_turns_a_calm_sea_into_no_go(self):
        out = risk(_calm(cyclone_distance_km=180.0))

        assert out["risk_class"] is RiskClass.NO_GO
        assert "CYCLONE-A1" in out["fired_rules"]
        assert "cyclone" in out["hazard_flags"]

    def test_a_cyclone_outside_the_radius_leaves_the_sea_state_verdict(self):
        out = risk(_calm(cyclone_distance_km=420.0))

        assert out["risk_class"] is RiskClass.SAFE
        assert "CYCLONE-A1" not in out["fired_rules"]

    def test_no_hazard_input_is_not_read_as_a_hazard(self):
        out = risk(_calm())

        assert out["risk_class"] is RiskClass.SAFE

    def test_the_capsule_carries_the_same_no_go_and_cyclone_flag(self):
        out = codec(_calm(cyclone_distance_km=180.0))
        cap = decode(from_base32(out["capsule_bits"]))

        assert cap.risk_class == "no_go"
        assert "cyclone" in cap.hazards

    def test_the_narration_names_the_hazard_and_passes_the_firewall(self):
        out = evidence(_calm(cyclone_distance_km=180.0))

        assert out["firewall_passed"]
        assert out["narration"].startswith("NO-GO.")
        assert "cyclone distance 180 km" in out["narration"]
        cyclone = [i for i in out["evidence"]["items"] if i["key"] == "cyclone_distance"]
        assert cyclone and cyclone[0]["rule_id"] == "CYCLONE-A1"


class TestOtherOverrides:
    def test_a_tsunami_alert_is_no_go(self):
        out = risk(_calm(tsunami_alert=True))

        assert out["risk_class"] is RiskClass.NO_GO
        assert "TSUNAMI-A3" in out["fired_rules"]

    def test_lightning_inside_the_radius_is_no_go(self):
        out = risk(_calm(lightning_distance_km=20.0))

        assert out["risk_class"] is RiskClass.NO_GO
        assert "LIGHTNING-A2" in out["fired_rules"]
