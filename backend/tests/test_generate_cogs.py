"""write_cog is the one piece of generate_cogs.py that doesn't need live
network — a small synthetic DataArray in, a real georeferenced COG out. The
live Copernicus call itself is exercised manually (python -m
dhruva.geo.generate_cogs), not in CI, matching how no existing test hits
Copernicus live.

Fixtures use latitude/longitude as the dim names — the real names Copernicus
data carries (copernicus.py's own _nearest_wet/_read_point already read
fields this way). An earlier version of this file used lat/lon, a guess from
registry.yaml's lat_min/lon_min KEY naming rather than the real data; it
passed against itself but the live script then failed with KeyError: 'lat'
the first time it ran against actual Copernicus output. Fixed here too, so
the tests can't drift back to testing an assumption instead of reality.
"""

from pathlib import Path

import numpy as np
import rasterio
import xarray as xr

from dhruva.geo.generate_cogs import write_cog


def test_write_cog_produces_a_valid_georeferenced_single_band_file(tmp_path):
    lat = np.linspace(6.0, 24.0, 10)
    lon = np.linspace(66.0, 94.0, 10)
    data = np.random.rand(10, 10).astype("float32")
    da = xr.DataArray(
        data, coords={"latitude": lat, "longitude": lon}, dims=["latitude", "longitude"], name="sst"
    )

    out = tmp_path / "sst.tif"
    write_cog(da, out)

    assert out.exists()
    with rasterio.open(out) as src:
        assert src.count == 1
        assert src.crs.to_epsg() == 4326
        # Bounds are pixel EDGES, not coordinate-array min/max — with only 10
        # points across each axis they legitimately extend half a pixel width
        # beyond the outermost coordinate on every side. A tighter check here
        # would be wrong, not stricter; DEMO_BBOX's real data has hundreds of
        # points, so this half-pixel margin is negligible there in practice.
        lat_px = (24.0 - 6.0) / 9
        lon_px = (94.0 - 66.0) / 9
        bounds = src.bounds
        assert 66.0 - lon_px <= bounds.left <= bounds.right <= 94.0 + lon_px
        assert 6.0 - lat_px <= bounds.bottom <= bounds.top <= 24.0 + lat_px


def test_write_cog_is_north_up_not_upside_down(tmp_path):
    """Regression test for a real bug found while implementing this: this
    project's own data-plane convention stores latitude ASCENDING
    (IMPLEMENTATION.md phase 2: "lat ascending, lon in -180..180"), but
    standard north-up GeoTIFF/COG readers — TiTiler included — require row 0
    of the file to be the NORTHERNMOST latitude (a negative Y-resolution in
    the affine transform). Writing an ascending-latitude array through
    rioxarray as-is, verified empirically by writing a known asymmetric
    pattern and reading the bytes back, produced a file with south at the top
    and north at the bottom — correctly georeferenced by coordinate, but
    rendered upside down by any standard viewer. This test pins the fix
    (sortby("latitude", ascending=False) before writing) so it cannot
    silently regress.
    """
    lat = np.linspace(6.0, 24.0, 10)  # ascending: index 0 = south, index 9 = north
    lon = np.linspace(66.0, 94.0, 10)
    data = np.zeros((10, 10), dtype="float32")
    for i in range(10):
        data[i, :] = i  # row i's value = i; the lat=24 (north) row must read ~9

    da = xr.DataArray(
        data, coords={"latitude": lat, "longitude": lon}, dims=["latitude", "longitude"], name="sst"
    )
    out = tmp_path / "orientation.tif"
    write_cog(da, out)

    with rasterio.open(out) as src:
        arr = src.read(1)
        assert arr[0, 0] == 9.0, "file top must be the northernmost row"
        assert arr[-1, 0] == 0.0, "file bottom must be the southernmost row"
        assert src.transform.e < 0, "Y-resolution must be negative (north-up)"
        assert src.bounds.bottom < src.bounds.top


def test_write_cog_creates_missing_parent_directories(tmp_path: Path):
    lat = np.linspace(6.0, 24.0, 4)
    lon = np.linspace(66.0, 94.0, 4)
    da = xr.DataArray(
        np.random.rand(4, 4).astype("float32"),
        coords={"latitude": lat, "longitude": lon},
        dims=["latitude", "longitude"],
    )
    out = tmp_path / "nested" / "dir" / "wave_height.tif"
    write_cog(da, out)
    assert out.exists()
