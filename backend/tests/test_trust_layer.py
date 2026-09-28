"""The trust layer: an impossible reading never reaches a verdict, and an alert
the engine cannot evaluate never reads as safety."""

import datetime as dt
from pathlib import Path

import pytest

from dhruva.graph.state import RiskClass, initial_state
from dhruva.risk.rules import assess
from dhruva.sources.base import FetchOutcome, Observation
from dhruva.sources.conditions import conditions_at
from dhruva.sources.plausibility import BOUNDS, implausible
from dhruva.sources.registry import Registry, SourceKind, Variable

NOW = dt.datetime(2026, 9, 29, 6, tzinfo=dt.UTC)


def obs(var: Variable, value: float, unit: str, dataset: str = "test_ds") -> Observation:
    return Observation(
        variable=var,
        value=value,
        unit=unit,
        dataset_id=dataset,
        upstream_dataset_id=dataset,
        valid_time=NOW,
        cell_lat=11.05,
        cell_lon=79.95,
        requested_lat=11.05,
        requested_lon=79.95,
        grid_resolution_deg=0.1,
        fetched_at=NOW,
    )


class TestPlausibility:
    def test_the_bay_of_bengal_cannot_be_2_6_degrees(self):
        """Seen live in another SIH team's demo."""
        assert implausible(obs(Variable.SST, 2.6, "degC")) is not None

    def test_a_marine_heatwave_is_extreme_not_impossible(self):
        assert implausible(obs(Variable.SST, 32.8, "degC")) is None

    @pytest.mark.parametrize(
        ("var", "value", "unit"),
        [
            (Variable.WAVE_HEIGHT, -0.5, "m"),
            (Variable.WAVE_HEIGHT, 45.0, "m"),
            (Variable.WIND_SPEED, 400.0, "kt"),
            (Variable.WIND_DIRECTION, 540.0, "degree"),
            (Variable.CHLOROPHYLL, -1.0, "mg m-3"),
        ],
    )
    def test_impossible_readings_are_named(self, var, value, unit):
        reason = implausible(obs(var, value, unit))
        assert reason is not None and var.value in reason

    def test_nan_never_becomes_a_reading(self):
        """Refused earlier still: Observation will not hold a non-finite value."""
        with pytest.raises(ValueError):
            obs(Variable.WAVE_HEIGHT, float("nan"), "m")

    def test_a_9_m_sea_is_kept_so_the_verdict_can_see_it(self):
        assert implausible(obs(Variable.WAVE_HEIGHT, 9.0, "m")) is None

    def test_every_sea_state_variable_has_bounds(self):
        for var in (Variable.SST, Variable.WAVE_HEIGHT, Variable.WIND_SPEED, Variable.CHLOROPHYLL):
            assert var in BOUNDS


class _Fixed:
    """An adapter that answers with whatever it was given."""

    def __init__(self, observations: list[Observation]) -> None:
        self._obs = observations

    async def fetch(self, entry, variables, lat, lon, when):
        return FetchOutcome(observations=[o for o in self._obs if o.dataset_id == entry.id])


async def test_an_impossible_reading_is_dropped_and_recorded():
    registry = Registry.load(Path(__file__).resolve().parents[2] / "data" / "registry.yaml")
    bad = obs(Variable.WAVE_HEIGHT, -3.0, "m", dataset="open_meteo_marine")
    result = await conditions_at(
        11.05,
        79.95,
        NOW,
        registry=registry,
        adapters={SourceKind.OPEN_METEO: _Fixed([bad])},
        variables=(Variable.WAVE_HEIGHT,),
    )
    assert Variable.WAVE_HEIGHT not in result.primary
    assert any("implausible wave_height" in e.error for e in result.errors)


def _state(**kw):
    s = initial_state("q", 11.05, 79.95, **kw)
    s["observations"] = [obs(Variable.WAVE_HEIGHT, 0.3, "m"), obs(Variable.WIND_SPEED, 5.0, "kt")]
    return s


class TestDefaultDeny:
    def test_a_calm_sea_with_no_alert_is_safe(self):
        assert assess(_state()).risk_class is RiskClass.SAFE

    def test_an_unrecognised_alert_is_at_least_caution(self):
        a = assess(_state(alerts=["storm_surge"]))
        assert a.risk_class is RiskClass.CAUTION
        assert "ALERT-C0" in a.rule_ids

    def test_a_cyclone_alert_with_no_position_is_not_ignored(self):
        a = assess(_state(alerts=["cyclone"]))
        assert a.risk_class is RiskClass.CAUTION

    def test_a_tsunami_alert_is_absolute(self):
        a = assess(_state(alerts=["Tsunami"]))
        assert a.risk_class is RiskClass.NO_GO
        assert "TSUNAMI-A3" in a.rule_ids

    def test_a_located_cyclone_is_judged_by_distance_not_denied(self):
        near = assess(_state(alerts=["cyclone"], cyclone_distance_km=120))
        far = assess(_state(alerts=["cyclone"], cyclone_distance_km=900))
        assert near.risk_class is RiskClass.NO_GO
        assert far.risk_class is RiskClass.SAFE
        assert "ALERT-C0" not in far.rule_ids

    def test_an_alert_never_softens_a_rough_sea(self):
        s = _state(alerts=["storm_surge"])
        s["observations"] = [
            obs(Variable.WAVE_HEIGHT, 4.5, "m"),
            obs(Variable.WIND_SPEED, 5.0, "kt"),
        ]
        assert assess(s).risk_class is RiskClass.NO_GO
