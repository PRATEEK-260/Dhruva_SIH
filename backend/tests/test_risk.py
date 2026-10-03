"""The risk engine decides what a crew acts on, so these tests are about the
ways a verdict can be wrong in a direction that matters: too safe."""

import datetime as dt

import pytest

from dhruva.graph.state import BoatClass, RiskClass, initial_state
from dhruva.risk.rules import assess
from dhruva.risk.thresholds import PROVISIONAL, thresholds_for
from dhruva.sources.base import Observation
from dhruva.sources.registry import Variable

NOW = dt.datetime(2026, 9, 12, tzinfo=dt.UTC)


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


def _state(
    wave: float | None = None, wind: float | None = None, boat: BoatClass = BoatClass.FRP_UNDER_12M
):
    s = initial_state("can I go out?", 11.05, 79.95, when=NOW, boat_class=boat)
    obs: list[Observation] = []
    if wave is not None:
        obs.append(_obs(Variable.WAVE_HEIGHT, wave, "m"))
    if wind is not None:
        obs.append(_obs(Variable.WIND_SPEED, wind, "kt"))
    s["observations"] = obs
    return s


class TestPerClassThresholds:
    def test_calm_sea_is_safe(self):
        r = assess(_state(wave=0.5, wind=8.0))
        assert r.risk_class is RiskClass.SAFE

    def test_wave_at_the_caution_threshold_is_caution(self):
        """The boundary itself must trip, not sit one side of it."""
        r = assess(_state(wave=2.0, wind=8.0))
        assert r.risk_class is RiskClass.CAUTION
        assert "WAVE-C2" in r.rule_ids

    def test_wave_at_the_no_go_threshold_is_no_go(self):
        r = assess(_state(wave=3.0, wind=8.0))
        assert r.risk_class is RiskClass.NO_GO
        assert "WAVE-N3" in r.rule_ids

    def test_wind_alone_can_force_caution(self):
        r = assess(_state(wave=0.4, wind=22.0))
        assert r.risk_class is RiskClass.CAUTION
        assert "WIND-C2" in r.rule_ids

    def test_the_worst_rule_wins(self):
        """Calm sea plus a gale is not calm."""
        r = assess(_state(wave=0.3, wind=30.0))
        assert r.risk_class is RiskClass.NO_GO

    def test_a_bigger_boat_gets_a_higher_bar(self):
        """2.6 m stops an FRP boat and does not stop a deep-sea trawler."""
        assert (
            assess(_state(wave=2.6, wind=8.0, boat=BoatClass.FRP_UNDER_12M)).risk_class
            is RiskClass.CAUTION
        )
        assert (
            assess(_state(wave=2.6, wind=8.0, boat=BoatClass.DEEP_SEA_OVER_20M)).risk_class
            is RiskClass.SAFE
        )

    @pytest.mark.parametrize("boat", list(BoatClass))
    def test_every_class_has_ordered_thresholds(self, boat):
        t = thresholds_for(boat)
        assert t.caution_wave_m < t.no_go_wave_m
        assert t.caution_wind_kt < t.no_go_wind_kt


class TestAbsoluteOverrides:
    def test_a_cyclone_overrides_a_calm_sea(self):
        r = assess(_state(wave=0.3, wind=5.0), cyclone_distance_km=250)
        assert r.risk_class is RiskClass.NO_GO
        assert "CYCLONE-A1" in r.rule_ids
        assert "cyclone" in r.hazard_flags

    def test_a_cyclone_beyond_the_radius_does_not_fire(self):
        r = assess(_state(wave=0.3, wind=5.0), cyclone_distance_km=400)
        assert r.risk_class is RiskClass.SAFE

    def test_lightning_inside_50_km_overrides(self):
        r = assess(_state(wave=0.3, wind=5.0), lightning_distance_km=30)
        assert r.risk_class is RiskClass.NO_GO
        assert "LIGHTNING-A2" in r.rule_ids

    def test_a_tsunami_alert_overrides_everything(self):
        r = assess(_state(wave=0.1, wind=2.0), tsunami_alert=True)
        assert r.risk_class is RiskClass.NO_GO
        assert "TSUNAMI-A3" in r.rule_ids

    def test_an_override_short_circuits_the_sea_state_rules(self):
        """The message must name the hazard, not the wave height."""
        r = assess(_state(wave=0.3, wind=5.0), tsunami_alert=True)
        assert r.rule_ids == ["TSUNAMI-A3"]
        assert r.deciding_rule is not None
        assert "Tsunami" in r.deciding_rule.message


class TestMissingDataIsNotSafety:
    def test_no_wave_data_is_unknown_not_safe(self):
        """The dangerous failure is silent. Not knowing must never read as safe."""
        r = assess(_state(wave=None, wind=5.0))
        assert r.risk_class is RiskClass.UNKNOWN
        assert "DATA-U0" in r.rule_ids

    def test_no_data_at_all_is_unknown(self):
        r = assess(_state())
        assert r.risk_class is RiskClass.UNKNOWN

    def test_unknown_does_not_mask_a_real_no_go(self):
        """Missing wind must not downgrade a no-go sea to merely unknown."""
        r = assess(_state(wave=3.5, wind=None))
        assert r.risk_class is RiskClass.NO_GO


class TestTraceability:
    def test_every_verdict_names_the_rule_that_set_it(self):
        r = assess(_state(wave=2.4, wind=8.0))
        assert r.deciding_rule is not None
        assert r.deciding_rule.rule_id == "WAVE-C2"
        assert r.deciding_rule.threshold == pytest.approx(2.0)
        assert r.deciding_rule.value == pytest.approx(2.4)

    def test_assessments_declare_the_thresholds_are_provisional(self):
        """These are placeholders, not INCOIS criteria, and anything showing a
        verdict to a person needs to be able to say so."""
        assert assess(_state(wave=1.0, wind=5.0)).provisional is PROVISIONAL is True


class TestCitedLimits:
    """Upgrade 4: wind and the 4.0 m sea are IMD's own fishermen-warning
    criteria (Marine Weather Services SOP 7.1); small-boat wave limits are
    stricter and stay provisional, and each verdict says which it used."""

    def test_wind_limits_are_imds_for_every_class(self):
        from dhruva.risk.thresholds import IMD_WIND_CAUTION_KT, IMD_WIND_NO_GO_KT

        for boat in BoatClass:
            t = thresholds_for(boat)
            assert (t.caution_wind_kt, t.no_go_wind_kt) == (IMD_WIND_CAUTION_KT, IMD_WIND_NO_GO_KT)
        assert IMD_WIND_NO_GO_KT * 1.852 > 45 > (IMD_WIND_NO_GO_KT - 0.1) * 1.852

    def test_no_class_waves_past_imds_very_rough_sea(self):
        for boat in BoatClass:
            assert thresholds_for(boat).no_go_wave_m <= 4.0

    def test_a_wind_no_go_cites_the_sop(self):
        r = assess(_state(wave=0.5, wind=25.0))
        rule = next(x for x in r.fired if x.rule_id == "WIND-N3")
        assert rule.source == "IMD Marine Weather Services SOP, 7.1(ii)"

    def test_a_small_boat_wave_limit_is_provisional_and_says_so(self):
        r = assess(_state(wave=2.2, wind=8.0))
        wave = next(x for x in r.fired if x.rule_id == "WAVE-C2")
        assert wave.source is None and r.provisional

    def test_a_large_boat_at_imds_sea_limit_is_cited(self):
        r = assess(_state(wave=4.1, wind=8.0, boat=BoatClass.DEEP_SEA_OVER_20M))
        wave = next(x for x in r.fired if x.rule_id == "WAVE-N3")
        assert wave.source == "IMD Marine Weather Services SOP, 7.1(iii)"

    def test_the_evidence_row_carries_the_source(self):
        from dhruva.evidence.schema import build_bundle

        s = _state(wave=0.5, wind=25.0)
        row = build_bundle(s["observations"], assess(s)).by_key("wind_speed")
        assert (
            row is not None and row.threshold_source == "IMD Marine Weather Services SOP, 7.1(ii)"
        )

    def test_the_sop_copy_matches_its_hash(self):
        import hashlib
        from pathlib import Path

        from dhruva.risk.thresholds import SOP_WIND

        pdf = Path(__file__).resolve().parents[2] / SOP_WIND.local_copy
        assert hashlib.sha256(pdf.read_bytes()).hexdigest() == SOP_WIND.sha256
