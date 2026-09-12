"""The 145-bit capsule codec.

The audit checklist in .claude/agents/capsule-auditor.md is the spec for this
file: total width exactly 145 with no overlap, every quantiser clamps, round-trip
fidelity over a corpus, and a decoder that is pure.
"""

import itertools
import random

import pytest

from dhruva.codec.codec import (
    CAPSULE_BYTES,
    Capsule,
    bit_budget,
    decode,
    encode,
    from_base32,
    from_hex,
    saturating_fields,
    to_base32,
    to_hex,
)
from dhruva.codec.fields import (
    BY_NAME,
    FIELDS,
    SEGMENT_BITS,
    TOTAL_BITS,
    ZONE_STEP,
    bitmap_hazards,
    compass_index,
    fields_to_position,
    hazard_bitmap,
    offsets,
    position_to_fields,
    total_bits,
)

# The offsets written in IMPLEMENTATION.md. The code computes its own from the
# widths; this asserts the two agree, which is what stops the spec and the
# implementation drifting.
SPEC_OFFSETS = {
    "msg_type": 0,
    "schema_ver": 4,
    "issue_slot": 7,
    "valid_hours": 17,
    "zone_id": 21,
    "lat_offset": 41,
    "lon_offset": 49,
    "risk_class": 57,
    "hazard_flags": 59,
    "wave_hs": 67,
    "wind_kt": 72,
    "wind_dir": 78,
    "curr_kt": 82,
    "curr_dir": 87,
    "sst": 91,
    "chl_class": 96,
    "pfz_bearing": 98,
    "pfz_dist_nm": 102,
    "pfz_conf": 108,
    "bnd_dist_nm": 110,
    "bnd_type": 115,
    "bnd_eta_min": 117,
    "reason_code": 125,
    "evidence_hash": 133,
}


def _demo() -> Capsule:
    """The plan's demo advisory, on the quantiser grid."""
    return Capsule(
        msg_type="advisory",
        schema_ver=1,
        issue_slot=417,
        valid_hours=6,
        lat=11.05,
        lon=79.95,
        risk_class="caution",
        hazards=["wave", "current"],
        wave_hs_m=2.5,
        wind_kt=18,
        wind_dir_deg=315.0,
        curr_kt=0.8,
        curr_dir_deg=90.0,
        sst_c=29.5,
        chl_class="high",
        pfz_bearing_deg=225.0,
        pfz_dist_nm=12,
        pfz_conf=2,
        bnd_dist_nm=24,
        bnd_type="imbl",
        bnd_eta_min=34,
        reason_code=41,
        evidence_hash=0xABC,
    )


class TestBitBudget:
    def test_total_is_exactly_145_bits(self):
        assert total_bits() == TOTAL_BITS == 145

    def test_it_fits_one_navic_segment_with_the_stated_headroom(self):
        b = bit_budget()
        assert b["segment"] == SEGMENT_BITS == 220
        assert b["free"] == 75

    def test_the_payload_is_19_bytes(self):
        assert CAPSULE_BYTES == 19
        assert len(encode(_demo())) == 19

    def test_no_field_overlaps_another(self):
        """Offsets are recomputed from widths rather than trusted."""
        off = offsets()
        spans = sorted((off[f.name], off[f.name] + f.width) for f in FIELDS)
        for (_, end), (start, _) in itertools.pairwise(spans):
            assert end == start, f"gap or overlap at bit {end}"

    def test_computed_offsets_match_the_written_spec(self):
        assert offsets() == SPEC_OFFSETS


class TestClampingNeverWraps:
    """The worst bug this project could ship. A 9 m sea that wraps to calm is
    read by a crew as permission to sail."""

    def test_a_nine_metre_sea_saturates_rather_than_wrapping(self):
        c = _demo()
        c.wave_hs_m = 9.0
        out = decode(encode(c))
        assert out.wave_hs_m == pytest.approx(7.75)
        assert out.wave_hs_m > 3.0, "must still read as dangerous"

    def test_a_hurricane_wind_saturates_at_the_top(self):
        c = _demo()
        c.wind_kt = 120
        assert decode(encode(c)).wind_kt == 63

    def test_a_negative_value_clamps_to_zero_not_to_the_top(self):
        c = _demo()
        c.wave_hs_m = -5.0
        assert decode(encode(c)).wave_hs_m == pytest.approx(0.0)

    def test_sst_below_the_floor_clamps_to_the_floor(self):
        c = _demo()
        c.sst_c = 5.0
        assert decode(encode(c)).sst_c == pytest.approx(18.0)

    def test_sst_above_the_ceiling_saturates(self):
        c = _demo()
        c.sst_c = 40.0
        assert decode(encode(c)).sst_c == pytest.approx(33.5)

    @pytest.mark.parametrize(
        ("name", "huge"),
        [
            ("wave_hs", 1e6),
            ("wind_kt", 1e6),
            ("curr_kt", 1e6),
            ("pfz_dist_nm", 1e6),
            ("bnd_dist_nm", 1e6),
            ("bnd_eta_min", 1e6),
        ],
    )
    def test_every_quantiser_clamps_at_its_own_rail(self, name, huge):
        f = BY_NAME[name]
        assert f.to_raw(huge) == f.max_raw
        assert f.to_raw(-huge) == 0

    def test_saturation_is_reported_so_the_ui_can_say_plus(self):
        c = _demo()
        c.wave_hs_m = 9.0
        c.wind_kt = 90
        hit = saturating_fields(c)
        assert "wave_hs" in hit and "wind_kt" in hit

    def test_an_in_range_value_is_not_reported_as_saturated(self):
        assert saturating_fields(_demo()) == []


class TestRoundTrip:
    def test_the_demo_advisory_survives_exactly(self):
        c = _demo()
        d = decode(encode(c))
        for attr in (
            "msg_type",
            "risk_class",
            "wave_hs_m",
            "wind_kt",
            "wind_dir_deg",
            "curr_kt",
            "sst_c",
            "chl_class",
            "pfz_bearing_deg",
            "pfz_dist_nm",
            "pfz_conf",
            "bnd_dist_nm",
            "bnd_type",
            "bnd_eta_min",
            "reason_code",
            "evidence_hash",
            "issue_slot",
            "valid_hours",
        ):
            assert getattr(d, attr) == getattr(c, attr), attr

    def test_hazard_flags_survive(self):
        c = _demo()
        c.hazards = ["wave", "lightning", "tsunami"]
        assert set(decode(encode(c)).hazards) == {"wave", "lightning", "tsunami"}

    def test_no_hazards_round_trips_as_empty(self):
        c = _demo()
        c.hazards = []
        assert decode(encode(c)).hazards == []

    def test_encode_is_deterministic(self):
        """The evidence hash is only auditable if the same advisory encodes the
        same way every time."""
        assert encode(_demo()) == encode(_demo())

    def test_a_random_corpus_round_trips(self):
        rng = random.Random(20260912)
        for _ in range(400):
            c = Capsule(
                msg_type=rng.choice(["advisory", "alert", "all_clear", "test"]),
                schema_ver=rng.randint(0, 7),
                issue_slot=rng.randint(0, 671),
                valid_hours=rng.randint(0, 15),
                lat=rng.uniform(6.0, 23.99),
                lon=rng.uniform(66.0, 93.99),
                risk_class=rng.choice(["safe", "caution", "no_go", "unknown"]),
                hazards=rng.sample(list(bitmap_hazards(255)), rng.randint(0, 4)),
                wave_hs_m=rng.randrange(0, 32) * 0.25,
                wind_kt=rng.randint(0, 63),
                wind_dir_deg=rng.randrange(16) * 22.5,
                curr_kt=round(rng.randrange(0, 32) * 0.1, 4),
                curr_dir_deg=rng.randrange(16) * 22.5,
                sst_c=18.0 + rng.randrange(0, 32) * 0.5,
                chl_class=rng.choice(["low", "moderate", "high", "very_high"]),
                pfz_bearing_deg=rng.randrange(16) * 22.5,
                pfz_dist_nm=rng.randint(0, 63),
                pfz_conf=rng.randint(0, 3),
                bnd_dist_nm=rng.randint(0, 31),
                bnd_type=rng.choice(["none", "imbl", "mpa", "closed"]),
                bnd_eta_min=rng.randint(0, 255),
                reason_code=rng.randint(0, 255),
                evidence_hash=rng.randint(0, 4095),
            )
            d = decode(encode(c))
            assert d.risk_class == c.risk_class
            assert d.wave_hs_m == pytest.approx(c.wave_hs_m)
            assert d.wind_kt == c.wind_kt
            assert d.sst_c == pytest.approx(c.sst_c)
            assert d.reason_code == c.reason_code
            assert d.bnd_eta_min == c.bnd_eta_min
            assert abs(d.lat - c.lat) < ZONE_STEP / 256 + 1e-9
            assert abs(d.lon - c.lon) < ZONE_STEP / 256 + 1e-9


class TestPosition:
    def test_position_resolves_to_about_22_metres(self):
        zid, la, lo = position_to_fields(11.0512, 79.9537)
        lat, lon = fields_to_position(zid, la, lo)
        assert abs(lat - 11.0512) * 111_320 < 25
        assert abs(lon - 79.9537) * 111_320 < 25

    def test_a_position_outside_the_eez_box_clamps_inside_it(self):
        """The grid only covers the Indian EEZ; a point outside must land on the
        edge rather than wrapping to the far side of the box."""
        zid, _, _ = position_to_fields(0.0, 0.0)
        lat, lon = fields_to_position(zid, 0, 0)
        assert 6.0 <= lat <= 24.0
        assert 66.0 <= lon <= 94.0


class TestCompass:
    def test_the_sixteen_points_round_trip(self):
        for i in range(16):
            assert compass_index(i * 22.5) == i

    def test_an_off_grid_bearing_snaps_to_the_nearest_point(self):
        """235 degrees is not a compass point. It snaps to 225 (SW), which is why
        a demo value must already sit on this grid."""
        assert compass_index(235.0) == 10
        assert compass_index(225.0) == 10

    def test_north_wraps_correctly(self):
        assert compass_index(359.0) == 0
        assert compass_index(360.0) == 0

    def test_hazard_bitmap_ignores_unknown_names(self):
        """A typo must not silently become a different hazard."""
        assert bitmap_hazards(hazard_bitmap(["wave", "nonsense"])) == ["wave"]


class TestTransports:
    def test_base32_round_trips(self):
        payload = encode(_demo())
        assert from_base32(to_base32(payload)) == payload

    def test_base32_is_qr_alphanumeric_safe(self):
        """QR alphanumeric mode covers A-Z and 0-9 only. Lowercase or padding
        would force byte mode and a denser, more fragile symbol."""
        text = to_base32(encode(_demo()))
        assert text.isupper() or text.isdigit()
        assert set(text) <= set("ABCDEFGHIJKLMNOPQRSTUVWXYZ234567")

    def test_hex_round_trips(self):
        payload = encode(_demo())
        assert from_hex(to_hex(payload)) == payload

    def test_every_transport_carries_identical_bits(self):
        """The NavIC claim is segment conformance, which is arithmetic and does
        not care which pipe the bytes came down."""
        payload = encode(_demo())
        assert from_base32(to_base32(payload)) == from_hex(to_hex(payload)) == payload


class TestDecoderIsPure:
    def test_decode_rejects_a_wrong_length_payload(self):
        with pytest.raises(ValueError, match="19 bytes"):
            decode(b"\x00" * 10)

    def test_the_decode_path_imports_nothing_that_needs_the_world(self):
        """The claim is that a phone with its radio off can expand a capsule. A
        decoder that reaches for the network, the filesystem or the clock breaks
        that on the day it matters."""
        import dhruva.codec.codec as mod
        import dhruva.codec.fields as fields_mod

        forbidden = {
            "socket",
            "http",
            "urllib",
            "httpx",
            "requests",
            "time",
            "datetime",
            "pathlib",
            "os",
            "open",
        }
        for module in (mod, fields_mod):
            names = set(vars(module))
            assert not (names & forbidden), f"{module.__name__} pulls in {names & forbidden}"

    def test_decoding_is_reproducible(self):
        payload = encode(_demo())
        assert decode(payload).as_dict() == decode(payload).as_dict()
