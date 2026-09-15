"""A raster layer is offered to the console only with its provenance row and
its file both present — pixels without a dataset and valid time may not render."""

from dhruva.geo.rasters import available_layers, read_manifest, write_manifest_entry

ENTRY = {
    "file": "sst.tif",
    "dataset_id": "cmems_mod_glo_phy_anfc_0.083deg_PT1H-m",
    "variable": "thetao",
    "unit": "degrees_C",
    "valid_time": "2026-09-14T00:00:00+00:00",
    "generated_at": "2026-09-14T01:00:00+00:00",
}


def test_missing_manifest_reads_as_empty(tmp_path):
    assert read_manifest(tmp_path) == {}
    assert available_layers(tmp_path) == []


def test_entry_without_its_file_is_not_offered(tmp_path):
    write_manifest_entry("sst", ENTRY, tmp_path)
    assert available_layers(tmp_path) == []


def test_entry_with_its_file_carries_provenance(tmp_path):
    write_manifest_entry("sst", ENTRY, tmp_path)
    (tmp_path / "sst.tif").write_bytes(b"cog")
    [layer] = available_layers(tmp_path)
    assert layer["layer"] == "sst"
    assert layer["dataset_id"] == ENTRY["dataset_id"]
    assert layer["valid_time"] == ENTRY["valid_time"]


def test_writing_one_layer_keeps_the_others(tmp_path):
    write_manifest_entry("sst", ENTRY, tmp_path)
    write_manifest_entry("wave_height", {**ENTRY, "file": "wave_height.tif"}, tmp_path)
    assert set(read_manifest(tmp_path)) == {"sst", "wave_height"}
