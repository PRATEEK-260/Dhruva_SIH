"""The brief's remaining example queries (answers/): zones to avoid, alerts,
tides, productive water and the straight-line route. For each: the normal
answer, the missing-data answer, the rule that keeps safety first, and the
numeric firewall in every pilot language."""

import datetime as dt
import json
import re

import pytest

from dhruva.answers import (
    PHRASES_DIR,
    Answer,
    avoid,
    languages,
    phrases,
    productive,
    render,
    route,
    thunder,
    tide,
)
from dhruva.evidence.firewall import validate
from dhruva.evidence.schema import EvidenceBundle
from dhruva.graph.state import BoatClass
from dhruva.sources.openmeteo_extra import turning_points

NOW = dt.datetime(2026, 10, 3, 6, 0, tzinfo=dt.UTC)
BOAT = {"lat": 11.05, "lon": 79.95, "boat_class": BoatClass.FRP_UNDER_12M}
PFZ = {"distance_nm": 7.6, "bearing_deg": 110.0, "lat": 11.01, "lon": 80.07, "uid": "x"}
STORM = {
    "distance_km": 84.2,
    "lat": 13.2,
    "lon": 81.2,
    "category": "Cyclonic Storm",
    "title": "National Bulletin No. 19 (BOB/06/2023)",
}
BOUNDARIES = [
    {
        "line_type": "Straight baseline",
        "territory1": "India",
        "distance_nm": 5.2,
        "closest_lat": 11.05,
        "closest_lon": 79.86,
        "name": "India straight baseline",
    },
    {
        "line_type": "Straight baseline",
        "territory1": "India",
        "distance_nm": 6.0,
        "closest_lat": 11.1,
        "closest_lon": 79.85,
        "name": "India straight baseline 2",
    },
    {
        "line_type": "Treaty",
        "territory1": "India",
        "territory2": "Sri Lanka",
        "distance_nm": 51.8,
        "closest_lat": 10.3,
        "closest_lon": 80.3,
        "name": "India - Sri Lanka",
    },
]
THUNDER = {
    "from": "2026-10-03T09:30:00+00:00",
    "dataset_id": "open_meteo_forecast",
    "cell_lat": 11.14,
    "cell_lon": 79.85,
}
TIDE = {
    "high": {"at": "2026-10-03T20:00:00+00:00"},
    "low": {"at": "2026-10-03T13:00:00+00:00"},
    "dataset_id": "open_meteo_marine",
    "cell_lat": 11.04,
    "cell_lon": 79.96,
}
PRODUCTIVE = {
    "chl_p75": 0.39,
    "chl_dataset": "chl 2026-10-01",
    "sst_dataset": "sst 2026-10-02",
    "cell": {"lat": 11.2, "lon": 80.2, "chl": 0.66, "sst": 29.64},
}
ROUTE = {"points": [(11.05, 79.95), (11.01, 80.07)], "waves": [0.22, 0.31]}


def _texts(a: Answer, lang: str = "en") -> str:
    return " ".join(line["text"] for line in render(a, lang)[0])


def _check(a: Answer, lang: str):
    from dhruva.evidence.schema import pfz_item

    lines, used = render(a, lang)
    assert used == lang
    narration = " ".join(line["text"] for line in lines)
    # The graph's bundle always carries the INCOIS row (graph/build.py _bundle).
    pfz_row = pfz_item({**PFZ, "issued_for": "2026-10-02"})
    result = validate(narration, EvidenceBundle(items=[*a.evidence, pfz_row]), language=lang)
    assert result.passed, (lang, narration, result.messages)


# ------------------------------------------------------------- zones to avoid
class TestAvoid:
    def test_warnings_come_before_lines(self):
        a = avoid.compose(
            {**BOAT, "cyclone_source": STORM, "boundaries": BOUNDARIES, "imd": {"status": "active"}}
        )
        parts = [p for p, _, _ in a.parts]
        assert parts[0] == "warning" and set(parts[1:]) == {"line"}
        text = _texts(a)
        assert "45 nautical miles" in text  # 84.2 km
        assert "Cyclonic Storm" in text

    def test_lines_are_distinct_with_direction_and_caveat(self):
        a = avoid.compose({**BOAT, "boundaries": BOUNDARIES, "imd": {"status": "none"}})
        text = _texts(a)
        assert text.count("straight baseline") == 1  # deduplicated
        assert "Sri Lanka is 52 nautical miles away, in the south-southeast direction" in text
        assert "No IMD cyclone warning is in force" in text
        assert text.endswith("Boundary lines are indicative, not legal lines.")

    def test_no_boundary_data_says_so(self):
        a = avoid.compose({**BOAT, "boundaries": [], "imd": {"status": "none"}})
        assert a.status == "no_data"
        assert "could not be checked" in _texts(a)

    def test_test_input_storm_is_labelled(self):
        a = avoid.compose({**BOAT, "cyclone_distance_km": 180.0, "boundaries": BOUNDARIES})
        assert _texts(a).startswith("Test input:")


# ------------------------------------------------------------------- alerts
class TestThunder:
    def test_forecast_thunderstorm_gives_its_time(self):
        a = thunder.compose({**BOAT, "thunder": THUNDER, "imd": {"status": "none"}})
        assert "Thunderstorms are forecast from 15:00" in _texts(a)
        assert _texts(a).endswith("This is a forecast, not observed lightning.")

    def test_none_forecast_says_the_window(self):
        a = thunder.compose(
            {**BOAT, "thunder": {**THUNDER, "from": None}, "imd": {"status": "none"}}
        )
        assert "No thunderstorm is forecast for the next 12 hours." in _texts(a)

    def test_unread_forecast_is_not_calm(self):
        a = thunder.compose({**BOAT, "thunder": None, "imd": {}})
        text = _texts(a)
        assert "could not be checked" in text and "No thunderstorm" not in text

    def test_forecast_thunderstorm_makes_the_verdict_caution(self):
        from dhruva.graph.state import RiskClass, initial_state
        from dhruva.risk.rules import assess
        from dhruva.sources.base import Observation
        from dhruva.sources.registry import Variable

        s = initial_state("q", 11.05, 79.95, when=NOW)
        s["observations"] = [
            Observation(
                variable=v,
                value=val,
                unit=u,
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
            for v, val, u in ((Variable.WAVE_HEIGHT, 0.4, "m"), (Variable.WIND_SPEED, 6.0, "kt"))
        ]
        assert assess(s).risk_class is RiskClass.SAFE
        s["thunder"] = THUNDER
        a = assess(s)
        assert a.risk_class is RiskClass.CAUTION and "TSTORM-C1" in a.rule_ids
        assert "squall" in a.hazard_flags


# -------------------------------------------------------------------- tides
class TestTide:
    def test_next_turns_in_order(self):
        text = _texts(tide.compose({**BOAT, "tide": TIDE}))
        assert text.startswith("Low water around 18:30, then high water around 01:30.")
        assert text.endswith("not for navigation.")

    def test_no_series_is_no_data(self):
        a = tide.compose({**BOAT, "tide": None})
        assert a.status == "no_data" and "could not be checked" in _texts(a)

    def test_turning_points_from_hourly_levels(self):
        hours = [NOW + dt.timedelta(hours=i) for i in range(7)]
        turns = turning_points(hours, [0.1, 0.4, 0.6, 0.5, 0.2, 0.1, 0.3])
        assert [(t["kind"], t["at"].hour) for t in turns] == [("high", 8), ("low", 11)]

    def test_gaps_are_not_turns(self):
        hours = [NOW + dt.timedelta(hours=i) for i in range(5)]
        assert turning_points(hours, [0.1, None, 0.6, None, 0.2]) == []


# --------------------------------------------------------- productive water
class TestProductive:
    def test_nearest_cell_and_the_incois_comparison(self):
        text = _texts(productive.compose({**BOAT, "productive": PRODUCTIVE, "pfz": PFZ}, False))
        assert "chlorophyll 0.66, sea 29.6 degrees" in text
        assert "official INCOIS fishing zone is 8 nautical miles" in text
        assert "provisional" in text

    def test_no_go_suggests_no_water(self):
        a = productive.compose({**BOAT, "productive": PRODUCTIVE, "pfz": PFZ}, True)
        assert "no fishing water is suggested" in _texts(a) and not a.evidence

    def test_no_satellite_data_says_so(self):
        a = productive.compose({**BOAT, "productive": None}, False)
        assert a.status == "no_data" and "could not be read" in _texts(a)

    def test_pick_needs_both_high_chlorophyll_and_the_range(self):
        import numpy as np

        chl = {
            "values": np.array([[0.1, 0.2], [0.9, 1.0]]),
            "lat": [11.0, 11.1],
            "lon": [80.0, 80.1],
        }
        hot = {"values": np.array([[28.0, 28.0], [31.5, 31.5]])}
        assert productive.pick(chl, hot, 11.0, 80.0)["cell"] is None  # rich but too warm
        ok = {"values": np.array([[28.0, 28.0], [28.0, 28.0]])}
        cell = productive.pick(chl, ok, 11.0, 80.0)["cell"]
        assert (cell["lat"], cell["lon"]) == (11.1, 80.1)  # the top quarter is one cell

    def test_cloud_is_never_productive(self):
        import numpy as np

        chl = {"values": np.full((2, 2), np.nan), "lat": [11.0, 11.1], "lon": [80.0, 80.1]}
        assert productive.pick(chl, {"values": np.full((2, 2), 28.0)}, 11.0, 80.0) is None


# -------------------------------------------------------------------- route
class TestRoute:
    def test_calm_line_is_offered_as_a_reference(self):
        a = route.compose({**BOAT, "pfz": PFZ, "route_check": ROUTE}, False)
        text = _texts(a)
        assert "highest waves along it are 0.31 metres, under your boat's limit of 2 metres" in text
        assert a.extra["line"] == [[79.95, 11.05], [80.07, 11.01]]
        assert text.endswith("straight-line reference, not navigation.")

    def test_rough_line_suggests_nothing(self):
        a = route.compose(
            {**BOAT, "pfz": PFZ, "route_check": {**ROUTE, "waves": [0.5, 2.4]}}, False
        )
        assert "No safe route is suggested" in _texts(a) and "line" not in a.extra

    def test_line_near_a_storm_suggests_nothing(self):
        storm = {**STORM, "lat": 11.3, "lon": 80.5}
        a = route.compose(
            {**BOAT, "pfz": PFZ, "route_check": ROUTE, "cyclone_source": storm}, False
        )
        assert "too close to IMD's storm" in _texts(a)

    def test_missing_waves_or_target_is_no_data(self):
        a = route.compose(
            {**BOAT, "pfz": PFZ, "route_check": {**ROUTE, "waves": [0.2, None]}}, False
        )
        assert a.status == "no_data"
        assert route.compose({**BOAT, "pfz": None}, False).status == "no_data"

    def test_no_go_suggests_no_route(self):
        assert "no route is suggested" in _texts(route.compose({**BOAT, "pfz": PFZ}, True))


# ----------------------------------------------------- every language, every number
def _all_answers():
    return [
        avoid.compose(
            {**BOAT, "cyclone_source": STORM, "boundaries": BOUNDARIES, "imd": {"status": "active"}}
        ),
        avoid.compose({**BOAT, "boundaries": BOUNDARIES, "imd": {"status": "none"}}),
        thunder.compose({**BOAT, "thunder": THUNDER, "cyclone_source": STORM}),
        thunder.compose({**BOAT, "thunder": {**THUNDER, "from": None}, "imd": {"status": "none"}}),
        tide.compose({**BOAT, "tide": TIDE}),
        productive.compose({**BOAT, "productive": PRODUCTIVE, "pfz": PFZ}, False),
        productive.compose(
            {**BOAT, "productive": {**PRODUCTIVE, "cell": None}, "pfz": None}, False
        ),
        route.compose({**BOAT, "pfz": PFZ, "route_check": ROUTE}, False),
        route.compose({**BOAT, "pfz": PFZ, "route_check": {**ROUTE, "waves": [0.5, 2.4]}}, False),
    ]


@pytest.mark.parametrize("lang", ["en", "ta", "ml", "or", "hi"])
def test_every_spoken_number_is_in_the_evidence(lang):
    for a in _all_answers():
        _check(a, lang)


@pytest.mark.parametrize("kind", ["avoid", "thunder", "tide", "productive", "route"])
def test_every_language_has_every_sentence_and_placeholder(kind):
    en = phrases(kind)["en"]
    assert set(languages(kind)) >= {"en", "ta", "ml", "or", "hi"}
    for lang in languages(kind):
        table = phrases(kind)[lang]
        for key, sentence in en.items():
            assert key in table, f"{kind}.{lang}.{key}"
            if isinstance(sentence, str):
                assert set(re.findall(r"{(\w+)}", table[key])) == set(
                    re.findall(r"{(\w+)}", sentence)
                ), f"{kind}.{lang}.{key}"


def test_no_phrase_names_depression_as_an_illness():
    """Machine translation rendered the weather 'Depression' as the illness in
    all four languages; the hand-fixed terms must stay fixed."""
    illness = {"மனச்சோர்வு", "വിഷാദം", "अवसाद", "ଅବସାଦ"}
    for path in PHRASES_DIR.glob("*.json"):
        text = path.read_text(encoding="utf-8")
        data = json.loads(text)
        for lang in ("ta", "ml", "hi", "or"):
            body = json.dumps(
                {k: v for k, v in data.get(lang, {}).items() if k != "_en"}, ensure_ascii=False
            )
            assert not any(w in body for w in illness), f"{path.name} {lang}"


def test_no_fixed_sentence_carries_a_number_of_its_own():
    """Every number must come from a placeholder. Hindi 'एक' and Odia 'ଏକ' are
    both 'one' and the article 'a', so a sentence using them as an article
    fails the firewall, or worse, passes by coincidence when some evidence
    value rounds to 1."""
    from dhruva.evidence.firewall import extract_numbers

    bad = []
    for path in sorted(PHRASES_DIR.glob("*.json")):
        data = json.loads(path.read_text(encoding="utf-8"))
        for lang, table in data.items():
            if lang.startswith("_"):
                continue
            for key, sentence in table.items():
                if not isinstance(sentence, str):
                    continue
                found, _ = extract_numbers(re.sub(r"{\w+}", "", sentence), lang)
                if found:
                    bad.append(f"{path.stem}.{lang}.{key}: {[t for t, _ in found]}")
    assert not bad, "\n".join(bad)
