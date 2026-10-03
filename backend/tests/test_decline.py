"""Query #7. The ways this answer can mislead a fisherman: calling an ordinary
year unusual, answering from too little history, naming a cause as fact, or
speaking a number the evidence does not hold."""

import datetime as dt
import re

import pytest

from dhruva.analytics.decline import (
    MIN_BASELINE_YEARS,
    WindowMean,
    answer,
    box_around,
    compare,
    evidence_items,
    languages,
    phrases,
    render,
    windows,
)
from dhruva.evidence.firewall import validate
from dhruva.evidence.schema import EvidenceBundle
from dhruva.sources.registry import Variable

END = dt.date(2026, 10, 1)
PFZ = {"distance_nm": 15.3, "bearing_deg": 92.0}


def _w(year: int, mean: float | None, days: int = 30) -> WindowMean:
    end = END.replace(year=year)
    return WindowMean(year, end - dt.timedelta(days=29), end, mean, days if mean is not None else 0)


def _chl(current: float | None, *baseline: float | None):
    return compare(
        Variable.CHLOROPHYLL,
        "mg m-3",
        _w(2026, current),
        [_w(2025 - i, b) for i, b in enumerate(baseline)],
        dataset_id="chl_set",
        upstream_dataset_id="upstream_chl",
    )


def _sst(current: float, *baseline: float):
    return compare(
        Variable.SST,
        "degC",
        _w(2026, current),
        [_w(2025 - i, b) for i, b in enumerate(baseline)],
        dataset_id="sst_set",
        upstream_dataset_id="upstream_sst",
    )


class TestWindows:
    def test_same_calendar_window_each_year(self):
        w = windows(END, 3)
        assert [y for y, _, _ in w] == [2026, 2025, 2024, 2023]
        for _, start, end in w:
            assert (end - start).days == 29
            assert (end.month, end.day) == (10, 1)

    def test_leap_day_moves_to_the_28th(self):
        w = windows(dt.date(2028, 2, 29), 1)
        assert w[1][2] == dt.date(2027, 2, 28)

    def test_box_is_about_twenty_km_square(self):
        lat_min, lat_max, lon_min, lon_max = box_around(11.05, 79.95)
        assert (lat_max - lat_min) * 111.32 == pytest.approx(20, abs=0.1)
        assert (lon_max - lon_min) * 111.32 * 0.9815 == pytest.approx(20, abs=0.2)


class TestUnusual:
    def test_a_real_drop_is_flagged(self):
        c = _chl(0.20, 0.50, 0.55, 0.45)
        assert c is not None
        assert c.unusual and c.direction == "down"
        assert c.change_pct == pytest.approx(-60.0)

    def test_an_ordinary_year_is_not_flagged(self):
        """Within the year-to-year spread is ordinary, however it compares with
        last year alone."""
        c = _chl(0.47, 0.50, 0.55, 0.45)
        assert c is not None
        assert not c.unusual and c.direction == "usual"

    def test_a_rise_is_flagged_up(self):
        c = _chl(0.90, 0.50, 0.55, 0.45)
        assert c is not None and c.direction == "up"


class TestNoData:
    def test_one_baseline_year_is_no_data(self):
        assert MIN_BASELINE_YEARS == 2
        assert _chl(0.2, 0.5) is None

    def test_cloud_gaps_do_not_count_as_years(self):
        """A year whose window had no clear-sky day is absent, not zero."""
        assert _chl(0.2, 0.5, None, None) is None

    def test_no_current_data_is_no_data(self):
        assert _chl(None, 0.5, 0.55, 0.45) is None

    def test_no_data_answer_says_so_and_nothing_else(self):
        a = answer(None, _sst(29.0, 28.0, 28.1, 27.9), PFZ)
        assert a.status == "no_data"
        lines = render(a, "en")
        assert "not enough satellite data" in lines[0]["text"]
        assert lines[-1]["text"] == "This compares the sea, not the catch."


class TestAnswer:
    def test_drop_gives_all_four_parts_and_the_caveat(self):
        a = answer(_chl(0.20, 0.50, 0.55, 0.45), _sst(29.6, 28.5, 28.7, 28.6), PFZ)
        lines = render(a, "en")
        assert [line["part"] for line in lines] == [
            "normal",
            "changed",
            "changed",
            "reason",
            "todo",
            "caveat",
        ]
        text = " ".join(line["text"] for line in lines)
        assert "usually about 0.5 milligrams" in text
        assert "0.2, clearly lower than the average of the last 3 years" in text
        assert "1 degrees Celsius warmer" in text
        assert "15 nautical miles to the east" in text

    def test_ordinary_sea_does_not_invent_a_reason(self):
        a = answer(_chl(0.5, 0.50, 0.55, 0.45), _sst(28.6, 28.5, 28.7, 28.6), None)
        text = " ".join(line["text"] for line in render(a, "en"))
        assert "may have a cause this does not measure" in text
        assert "no fresh INCOIS fishing zone" in text

    @pytest.mark.parametrize("lang", ["en", "ta", "ml", "or", "hi"])
    def test_wording_never_states_a_cause(self, lang):
        """The plan's banned wording, checked across every English sentence;
        translations are checked by a native speaker."""
        table = phrases()
        assert lang in table, f"{lang} phrases missing; run scripts/phrases.py"
        if lang != "en":
            return
        for key, sentence in table["en"].items():
            low = sentence.lower()
            for banned in ("because", "overfishing", "fish have left", "caused by"):
                assert banned not in low, f"{key}: {sentence}"

    def test_every_language_has_every_key_and_placeholder(self):
        en = phrases()["en"]
        for lang in languages():
            table = phrases()[lang]
            assert set(table) >= set(en), lang
            for key, sentence in en.items():
                assert set(re.findall(r"{(\w+)}", table[key])) == set(
                    re.findall(r"{(\w+)}", sentence)
                ), f"{lang}.{key}"

    def test_unknown_language_falls_back_to_english(self):
        a = answer(None, None, None)
        assert render(a, "xx") == render(a, "en")


class TestNumberCheck:
    @pytest.mark.parametrize("lang", ["en", "ta", "ml", "or", "hi"])
    @pytest.mark.parametrize(
        "chl,sst",
        [
            ((0.20, 0.50, 0.55, 0.45), (29.6, 28.5, 28.7, 28.6)),
            ((0.47, 0.50, 0.55, 0.45), (27.4, 28.5, 28.7, 28.6)),
            ((0.912, 0.513, 0.55, 0.45), (28.63, 28.5, 28.7, 28.6)),
        ],
    )
    def test_every_spoken_number_is_in_the_evidence(self, lang, chl, sst):
        a = answer(_chl(*chl), _sst(*sst), PFZ)
        bundle = EvidenceBundle(items=evidence_items(a, box_around(11.05, 79.95)))
        from dhruva.evidence.schema import pfz_item

        bundle.items.append(
            pfz_item(
                {
                    **PFZ,
                    "issued_for": "2026-09-27",
                    "uid": "x",
                    "lat": 11.1,
                    "lon": 80.2,
                }
            )
        )
        narration = " ".join(line["text"] for line in render(a, lang))
        check = validate(narration, bundle, language=lang)
        assert check.passed, (narration, check.messages)

    def test_a_fabricated_number_fails(self):
        a = answer(_chl(0.20, 0.50, 0.55, 0.45), None, None)
        bundle = EvidenceBundle(items=evidence_items(a, box_around(11.05, 79.95)))
        narration = " ".join(line["text"] for line in render(a, "en")) + " Catch fell 40 percent."
        assert not validate(narration, bundle).passed

    def test_evidence_rows_carry_window_and_years(self):
        a = answer(_chl(0.20, 0.50, 0.55, 0.45), None, None)
        rows = {i.key: i for i in evidence_items(a, box_around(11.05, 79.95))}
        assert rows["chlorophyll_30d"].window_end == END
        assert rows["chlorophyll_baseline"].baseline_years == [2023, 2024, 2025]
        assert rows["chlorophyll_30d"].dataset_id == "chl_set"


def test_no_go_holds_back_the_fishing_zone():
    """NO-GO outranks everything: a zone is never suggested over a hazard."""
    a = answer(_chl(0.20, 0.50, 0.55, 0.45), None, PFZ, no_go=True)
    lines = render(a, "en")
    todo = [line["text"] for line in lines if line["part"] == "todo"]
    assert todo == ["It is not safe to go to sea now, so no fishing zone is suggested."]
    assert "nautical miles" not in " ".join(line["text"] for line in lines)


class TestWindowMeans:
    """The fetch layer's averaging, on a synthetic grid shaped like a Copernicus
    daily L4 subset: time x latitude x longitude."""

    def _grid(self, values_by_year: dict[int, float | None]):
        import numpy as np
        import pandas as pd
        import xarray as xr

        times, frames = [], []
        for year, value in values_by_year.items():
            days = pd.date_range(dt.date(year, 9, 2), dt.date(year, 10, 1), freq="D")
            for d in days:
                times.append(d)
                frames.append(np.full((3, 3), np.nan if value is None else value))
        return xr.Dataset(
            {"CHL": (("time", "latitude", "longitude"), np.stack(frames))},
            coords={
                "time": times,
                "latitude": [10.95, 11.05, 11.15],
                "longitude": [79.85, 79.95, 80.05],
            },
        )

    def _source(self, offset: float = 0.0):
        from dhruva.analytics.baseline import BaselineSource

        return BaselineSource(Variable.CHLOROPHYLL, "chl_set", "upstream", "CHL", "mg m-3", offset)

    def test_each_window_gets_its_own_year(self):
        from dhruva.analytics.baseline import window_means

        ds = self._grid({2023: 0.4, 2024: 0.5, 2025: 0.6, 2026: 0.2})
        means = window_means(ds, self._source(), windows(END, 3))
        assert [m.year for m in means] == [2026, 2025, 2024, 2023]
        assert [m.mean for m in means] == pytest.approx([0.2, 0.6, 0.5, 0.4])
        assert all(m.days == 30 for m in means)

    def test_a_fully_cloudy_window_is_missing_not_zero(self):
        from dhruva.analytics.baseline import window_means

        ds = self._grid({2023: None, 2024: 0.5, 2025: 0.6, 2026: 0.2})
        means = window_means(ds, self._source(), windows(END, 3))
        assert means[3].mean is None and means[3].days == 0

    def test_partial_cloud_counts_the_clear_cells_and_days(self):
        import numpy as np

        from dhruva.analytics.baseline import window_means

        ds = self._grid({2026: 0.3})
        chl = ds["CHL"].values
        chl[:10] = np.nan  # ten fully cloudy days
        chl[10:, 0, 0] = 9.0  # one cell different on the clear days
        means = window_means(ds, self._source(), windows(END, 0))
        assert means[0].days == 20
        assert means[0].mean == pytest.approx((9.0 + 8 * 0.3) / 9)

    def test_kelvin_offset_is_applied(self):
        from dhruva.analytics.baseline import window_means

        ds = self._grid({2026: 302.15})
        means = window_means(ds, self._source(offset=-273.15), windows(END, 0))
        assert means[0].mean == pytest.approx(29.0)


class TestGraphNodes:
    """Query #7 through the graph's own nodes, with the fetch stubbed."""

    NOW = dt.datetime(2026, 10, 3, 6, 0, tzinfo=dt.UTC)

    def _state(self, wave: float = 0.5, wind: float = 8.0, pfz: dict | None = None):
        from dhruva.graph.state import Intent, initial_state
        from dhruva.sources.base import Observation

        s = initial_state(
            "why are there fewer fish here?", 11.05, 79.95, when=self.NOW, language="ta"
        )
        s["intent"] = Intent.DECLINE_ATTRIBUTION
        s["plan"] = {
            "intent": Intent.DECLINE_ATTRIBUTION,
            "nodes": ["discovery", "ocean", "weather", "geo"],
        }
        s["observations"] = [
            Observation(
                variable=v,
                value=val,
                unit=u,
                dataset_id="d",
                upstream_dataset_id="u",
                valid_time=self.NOW,
                cell_lat=11.05,
                cell_lon=79.95,
                requested_lat=11.05,
                requested_lon=79.95,
                grid_resolution_deg=0.083,
                fetched_at=self.NOW,
            )
            for v, val, u in ((Variable.WAVE_HEIGHT, wave, "m"), (Variable.WIND_SPEED, wind, "kt"))
        ]
        s["decline"] = {
            "chlorophyll": _chl(0.20, 0.50, 0.55, 0.45),
            "sst": _sst(29.6, 28.5, 28.7, 28.6),
            "box": box_around(11.05, 79.95),
        }
        s["pfz"] = pfz
        return s

    def test_evidence_node_speaks_the_comparison_and_passes_the_check(self):
        from dhruva.graph.build import evidence

        out = evidence(self._state())
        assert out["firewall_passed"], out["firewall_violations"]
        d = out["decline_answer"]
        assert d["status"] == "ok" and d["language"] == "ta"
        assert out["narration"] == " ".join(line["text"] for line in d["lines"])
        keys = {i["key"] for i in out["evidence"]["items"]}
        assert {"chlorophyll_30d", "chlorophyll_baseline", "sst_difference", "wave_height"} <= keys

    def test_no_go_suppresses_the_zone_in_the_graph_too(self):
        from dhruva.graph.build import evidence

        pfz = {**PFZ, "issued_for": "2026-10-01", "uid": "x", "lat": 11.1, "lon": 80.2}
        out = evidence(self._state(wave=9.0, wind=50.0, pfz=pfz))
        todo = [line for line in out["decline_answer"]["lines"] if line["part"] == "todo"]
        assert todo[0]["text"] == phrases()["ta"]["todo_no_go"]

    def test_capsule_hash_covers_the_decline_rows(self):
        """The capsule's evidence fingerprint is over what the card shows."""
        from dhruva.graph.build import codec

        plain = self._state()
        plain["decline"] = None
        assert codec(self._state())["capsule_bits"] != codec(plain)["capsule_bits"]

    def test_ocean_node_runs_the_comparison_not_a_point_fetch(self, monkeypatch):
        import asyncio

        from dhruva.analytics import baseline
        from dhruva.graph.build import ocean

        seen = {}

        async def fake(lat, lon, when, **kw):
            seen["at"] = (lat, lon, when)
            return {"chlorophyll": None, "sst": None, "box": box_around(lat, lon)}, []

        monkeypatch.setattr(baseline, "decline_changes", fake)
        out = asyncio.run(ocean(self._state()))
        assert seen["at"] == (11.05, 79.95, self.NOW)
        assert out["decline"]["chlorophyll"] is None
        assert "observations" not in out

    def test_trace_names_the_comparison(self):
        from dhruva.api.trace import build_trace
        from dhruva.graph.build import evidence

        s = self._state()
        s.update(evidence(s))
        lines = {t["node"]: t for t in build_trace(s)}
        assert lines["ocean"]["ran"]
        assert "same weeks in 2023-2025" in lines["ocean"]["line"]
        assert "below usual" in lines["ocean"]["line"]
        assert "needs the network" in lines["language"]["line"]

    def test_no_data_trace_says_so(self):
        from dhruva.api.trace import build_trace
        from dhruva.graph.build import evidence

        s = self._state()
        s["decline"] = {"chlorophyll": None, "sst": None, "box": box_around(11.05, 79.95)}
        s.update(evidence(s))
        assert s["decline_answer"]["status"] == "no_data"
        lines = {t["node"]: t for t in build_trace(s)}
        assert "No data" in lines["ocean"]["line"]
