"""Encode and decode the 145-bit capsule.

Both directions walk the same field list from fields.py in the same order, so
they cannot disagree about layout. Neither hardcodes an offset.

The decoder is PURE: no network, no filesystem, no clock, no imports beyond the
field table. That is not tidiness — the whole claim is that a phone with its
radio off can expand a capsule into a spoken advisory, and a decoder that reaches
for anything at all breaks that on the day it matters.
"""

from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from dataclasses import field as dc_field
from typing import Any

from dhruva.codec.fields import (
    BOUNDARY_TYPES,
    BY_NAME,
    CHL_CLASSES,
    FIELDS,
    MSG_TYPES,
    RISK_CLASSES,
    SEGMENT_BITS,
    TOTAL_BITS,
    bitmap_hazards,
    compass_index,
    enum_index,
    fields_to_position,
    hazard_bitmap,
    index_to_bearing,
    position_to_fields,
    total_bits,
)

CAPSULE_BYTES = (TOTAL_BITS + 7) // 8  # 19


@dataclass(slots=True)
class Capsule:
    """The decoded advisory. Plain values, ready to fill a template."""

    msg_type: str = "advisory"
    schema_ver: int = 1
    issue_slot: int = 0
    valid_hours: int = 6
    lat: float = 0.0
    lon: float = 0.0
    risk_class: str = "unknown"
    hazards: list[str] = dc_field(default_factory=list)
    wave_hs_m: float = 0.0
    wind_kt: int = 0
    wind_dir_deg: float = 0.0
    curr_kt: float = 0.0
    curr_dir_deg: float = 0.0
    sst_c: float = 18.0
    chl_class: str = "low"
    pfz_bearing_deg: float = 0.0
    pfz_dist_nm: int = 0
    pfz_conf: int = 0
    bnd_dist_nm: int = 0
    bnd_type: str = "none"
    bnd_eta_min: int = 0
    reason_code: int = 0
    evidence_hash: int = 0
    # Set by the encoder when a value hit a rail, so the UI can say "18+ kt".
    saturated: list[str] = dc_field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _raw_fields(c: Capsule) -> dict[str, int]:
    """Capsule to raw integers, one per field. Every quantiser clamps."""
    zid, lat_off, lon_off = position_to_fields(c.lat, c.lon)
    return {
        "msg_type": enum_index(MSG_TYPES, c.msg_type),
        "schema_ver": BY_NAME["schema_ver"].to_raw(c.schema_ver),
        "issue_slot": BY_NAME["issue_slot"].to_raw(c.issue_slot),
        "valid_hours": BY_NAME["valid_hours"].to_raw(c.valid_hours),
        "zone_id": zid,
        "lat_offset": lat_off,
        "lon_offset": lon_off,
        "risk_class": enum_index(RISK_CLASSES, c.risk_class, default=3),
        "hazard_flags": hazard_bitmap(c.hazards),
        "wave_hs": BY_NAME["wave_hs"].to_raw(c.wave_hs_m),
        "wind_kt": BY_NAME["wind_kt"].to_raw(c.wind_kt),
        "wind_dir": compass_index(c.wind_dir_deg),
        "curr_kt": BY_NAME["curr_kt"].to_raw(c.curr_kt),
        "curr_dir": compass_index(c.curr_dir_deg),
        "sst": BY_NAME["sst"].to_raw(c.sst_c),
        "chl_class": enum_index(CHL_CLASSES, c.chl_class),
        "pfz_bearing": compass_index(c.pfz_bearing_deg),
        "pfz_dist_nm": BY_NAME["pfz_dist_nm"].to_raw(c.pfz_dist_nm),
        "pfz_conf": BY_NAME["pfz_conf"].to_raw(c.pfz_conf),
        "bnd_dist_nm": BY_NAME["bnd_dist_nm"].to_raw(c.bnd_dist_nm),
        "bnd_type": enum_index(BOUNDARY_TYPES, c.bnd_type),
        "bnd_eta_min": BY_NAME["bnd_eta_min"].to_raw(c.bnd_eta_min),
        "reason_code": BY_NAME["reason_code"].to_raw(c.reason_code),
        "evidence_hash": BY_NAME["evidence_hash"].to_raw(c.evidence_hash),
    }


def saturating_fields(c: Capsule) -> list[str]:
    """Which values hit a rail. Quoting a saturated reading as exact is a lie of
    a different kind, so the caller is told."""
    hit: list[str] = []
    for name, value in (
        ("wave_hs", c.wave_hs_m),
        ("wind_kt", c.wind_kt),
        ("curr_kt", c.curr_kt),
        ("sst", c.sst_c),
        ("pfz_dist_nm", c.pfz_dist_nm),
        ("bnd_dist_nm", c.bnd_dist_nm),
        ("bnd_eta_min", c.bnd_eta_min),
    ):
        if BY_NAME[name].saturates(value):
            hit.append(name)
    return hit


def encode(c: Capsule) -> bytes:
    """Capsule to 19 bytes, MSB-first, the low 7 bits of the last byte padding."""
    raw = _raw_fields(c)
    acc = 0
    for f in FIELDS:
        value = raw[f.name] & f.max_raw  # already clamped; mask is belt and braces
        acc = (acc << f.width) | value
    acc <<= CAPSULE_BYTES * 8 - total_bits()  # left-align, pad the tail
    return acc.to_bytes(CAPSULE_BYTES, "big")


def decode(payload: bytes) -> Capsule:
    """19 bytes to a Capsule. Pure: no network, no filesystem, no clock."""
    if len(payload) != CAPSULE_BYTES:
        raise ValueError(f"capsule must be {CAPSULE_BYTES} bytes, got {len(payload)}")

    acc = int.from_bytes(payload, "big") >> (CAPSULE_BYTES * 8 - total_bits())
    raw: dict[str, int] = {}
    for f in reversed(FIELDS):
        raw[f.name] = acc & f.max_raw
        acc >>= f.width

    lat, lon = fields_to_position(raw["zone_id"], raw["lat_offset"], raw["lon_offset"])
    return Capsule(
        msg_type=MSG_TYPES[raw["msg_type"] % len(MSG_TYPES)],
        schema_ver=raw["schema_ver"],
        issue_slot=raw["issue_slot"],
        valid_hours=raw["valid_hours"],
        lat=lat,
        lon=lon,
        risk_class=RISK_CLASSES[raw["risk_class"]],
        hazards=bitmap_hazards(raw["hazard_flags"]),
        wave_hs_m=BY_NAME["wave_hs"].from_raw(raw["wave_hs"]),
        wind_kt=raw["wind_kt"],
        wind_dir_deg=index_to_bearing(raw["wind_dir"]),
        curr_kt=round(BY_NAME["curr_kt"].from_raw(raw["curr_kt"]), 4),
        curr_dir_deg=index_to_bearing(raw["curr_dir"]),
        sst_c=BY_NAME["sst"].from_raw(raw["sst"]),
        chl_class=CHL_CLASSES[raw["chl_class"]],
        pfz_bearing_deg=index_to_bearing(raw["pfz_bearing"]),
        pfz_dist_nm=raw["pfz_dist_nm"],
        pfz_conf=raw["pfz_conf"],
        bnd_dist_nm=raw["bnd_dist_nm"],
        bnd_type=BOUNDARY_TYPES[raw["bnd_type"]],
        bnd_eta_min=raw["bnd_eta_min"],
        reason_code=raw["reason_code"],
        evidence_hash=raw["evidence_hash"],
    )


# ------------------------------------------------------------- transports ----
# One wire format, three carriers. The bits are identical on all of them, which
# is the whole point: the NavIC claim is segment conformance, and conformance is
# arithmetic that does not care which pipe the bytes came down.


def to_base32(payload: bytes) -> str:
    """For QR. Base32 rather than base64: QR alphanumeric mode covers A-Z and
    0-9, so an uppercase base32 string encodes far more densely than mixed-case
    base64, and scanners misread fewer characters."""
    return base64.b32encode(payload).decode("ascii").rstrip("=")


def from_base32(text: str) -> bytes:
    padded = text.strip().upper()
    padded += "=" * (-len(padded) % 8)
    return base64.b32decode(padded)


def to_hex(payload: bytes) -> str:
    """For SMS and for reading aloud in a bug report."""
    return payload.hex().upper()


def from_hex(text: str) -> bytes:
    return bytes.fromhex(text.strip())


def bit_budget() -> dict[str, int]:
    return {
        "used": total_bits(),
        "segment": SEGMENT_BITS,
        "free": SEGMENT_BITS - total_bits(),
        "bytes": CAPSULE_BYTES,
    }
