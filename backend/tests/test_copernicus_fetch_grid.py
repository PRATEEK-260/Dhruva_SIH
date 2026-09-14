"""fetch_grid is the box-general core _subset already had, extracted so the
COG generator can call it directly instead of duplicating the kwarg-building
logic or reaching into another module's _-prefixed method. This test proves
the extraction is behaviour-preserving: _subset must still pass the identical
kwargs it always did, just routed through fetch_grid now.
"""

import datetime as dt
from unittest.mock import MagicMock, patch

from dhruva.sources.copernicus import fetch_grid


def test_fetch_grid_builds_the_expected_open_dataset_kwargs():
    fake_ds = MagicMock()
    fake_ds.load.return_value = "loaded"
    with patch("copernicusmarine.open_dataset", return_value=fake_ds) as mock_open:
        result = fetch_grid(
            "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
            ["thetao"],
            lat_min=6.0,
            lat_max=24.0,
            lon_min=66.0,
            lon_max=94.0,
            start=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
            end=dt.datetime(2026, 9, 14, 6, tzinfo=dt.UTC),
        )
    mock_open.assert_called_once_with(
        dataset_id="cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
        variables=["thetao"],
        minimum_latitude=6.0,
        maximum_latitude=24.0,
        minimum_longitude=66.0,
        maximum_longitude=94.0,
        start_datetime=dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
        end_datetime=dt.datetime(2026, 9, 14, 6, tzinfo=dt.UTC),
    )
    assert result == "loaded"


def test_fetch_grid_adds_credentials_only_when_given():
    fake_ds = MagicMock()
    fake_ds.load.return_value = "loaded"
    with patch("copernicusmarine.open_dataset", return_value=fake_ds) as mock_open:
        fetch_grid(
            "d",
            ["v"],
            lat_min=0,
            lat_max=1,
            lon_min=0,
            lon_max=1,
            start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            end=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            username="u",
            password="p",
        )
    assert mock_open.call_args.kwargs["username"] == "u"
    assert mock_open.call_args.kwargs["password"] == "p"


def test_fetch_grid_passes_extra_kwargs_through_untouched():
    """The **extra passthrough is what lets _subset's depth override still
    reach open_dataset after this extraction."""
    fake_ds = MagicMock()
    fake_ds.load.return_value = "loaded"
    with patch("copernicusmarine.open_dataset", return_value=fake_ds) as mock_open:
        fetch_grid(
            "d",
            ["v"],
            lat_min=0,
            lat_max=1,
            lon_min=0,
            lon_max=1,
            start=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            end=dt.datetime(2026, 1, 1, tzinfo=dt.UTC),
            minimum_depth=0.0,
            maximum_depth=1.0,
        )
    assert mock_open.call_args.kwargs["minimum_depth"] == 0.0
    assert mock_open.call_args.kwargs["maximum_depth"] == 1.0


def test_subset_delegates_to_fetch_grid_with_its_narrowed_tile():
    """The existing per-point path must be untouched by this refactor."""
    from dhruva.sources.cache import CacheKey
    from dhruva.sources.copernicus import CopernicusAdapter
    from dhruva.sources.registry import Registry

    # A real registry entry, not a hand-typed stand-in: keeps this test
    # exercising the actual DatasetEntry shape _subset() receives in
    # production, and stays pyright-clean without hand-modelling every
    # required field (spatial/temporal extents, variable specs) that entry
    # carries but this test does not otherwise care about.
    registry = Registry.load("data/registry.yaml")
    entry = registry.by_id("copernicus_phy_hourly")

    adapter = CopernicusAdapter()
    # CacheKey.for_point is what fetch() actually calls to narrow a point to
    # its enclosing tile — using it here keeps this key realistic.
    key = CacheKey.for_point(
        entry.dataset_id,
        11.05,
        79.95,
        dt.datetime(2026, 9, 14, tzinfo=dt.UTC),
        ["thetao"],
        tile_deg=1.0,
    )
    fake_ds = MagicMock()
    fake_ds.load.return_value = "loaded"
    with patch("copernicusmarine.open_dataset", return_value=fake_ds) as mock_open:
        adapter._subset(entry, ["thetao"], key)
    called = mock_open.call_args.kwargs
    assert called["minimum_latitude"] == key.lat_min
    assert called["maximum_latitude"] == key.lat_max
    # Surface-only for copernicus_phy_hourly, unchanged from before the refactor.
    assert called["minimum_depth"] == 0.0
    assert called["maximum_depth"] == 1.0
