"""The capsule field table — the single source of truth.

Encoder, decoder and docs/CAPSULE_SPEC.md are all generated from this list, so
they cannot drift apart. Offsets are computed from widths and never written down:
a hand-maintained offset column is a second copy of the same information, and the
two disagree eventually.

Total is 145 bits, inside a 220-bit NavIC L5 segment, leaving 75 free.

Every quantiser CLAMPS. Saturating a 9 m sea to the top of the scale reads as
"very rough"; wrapping it reads as "calm", and a crew acts on calm. That is the
worst bug this project could ship, so it is enforced in one place — `to_raw` —
rather than trusted to each field.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dc_field

TOTAL_BITS = 145
SEGMENT_BITS = 220

# Zone grid: the Indian EEZ box at 0.05 degrees.
ZONE_LAT_MIN, ZONE_LAT_MAX = 6.0, 24.0
ZONE_LON_MIN, ZONE_LON_MAX = 66.0, 94.0
ZONE_STEP = 0.05
ZONE_LON_CELLS = round((ZONE_LON_MAX - ZONE_LON_MIN) / ZONE_STEP)  # 560
ZONE_LAT_CELLS = round((ZONE_LAT_MAX - ZONE_LAT_MIN) / ZONE_STEP)  # 360

HAZARD_FLAGS = ("wave", "wind", "squall", "lightning", "cyclone", "current", "fog", "tsunami")

MSG_TYPES = ("advisory", "alert", "all_clear", "test")
RISK_CLASSES = ("safe", "caution", "no_go", "unknown")
BOUNDARY_TYPES = ("none", "imbl", "mpa", "closed")
CHL_CLASSES = ("low", "moderate", "high", "very_high")


@dataclass(frozen=True, slots=True)
class Field:
    """One field. `scale`/`offset` describe the quantiser: raw = (value - offset) / scale."""

    name: str
    width: int
    description: str
    encoding: str
    scale: float = 1.0
    offset: float = 0.0
    unit: str = ""
    choices: tuple[str, ...] | None = None
    derived: bool = dc_field(default=False)

    @property
    def max_raw(self) -> int:
        return (1 << self.width) - 1

    @property
    def max_value(self) -> float:
        return self.max_raw * self.scale + self.offset

    @property
    def min_value(self) -> float:
        return self.offset

    def to_raw(self, value: float | None) -> int:
        """Quantise, and CLAMP. Never wrap.

        A value above the top of the scale saturates at the top, which reads as
        "at least this bad". Wrapping would turn a 9 m sea into a calm one.

        None encodes as the bottom of the scale: it means the caller explicitly
        had nothing, and a capsule cannot express per-field absence — there is no
        spare bit for it. When the missing field is one a verdict rests on, the
        caller must set risk_class to unknown rather than let a zero speak.

        NaN and infinity RAISE. They are not measurements, they are the residue
        of a failed computation — an ocean model filling a land cell, a division
        that went wrong — and silently clamping NaN to zero would encode "calm
        sea" from a value that means "no idea". This project already refuses
        non-finite readings at the Observation boundary; this is the same rule at
        the last gate before the bits go out.
        """
        if value is None:
            return 0
        numeric = float(value)
        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            raise ValueError(
                f"{self.name}: refusing to encode a non-finite value ({value!r}). "
                "NaN or infinity here means a computation failed; encoding it as a "
                "number would put a fabricated reading on the wire."
            )
        raw = round((numeric - self.offset) / self.scale)
        return max(0, min(self.max_raw, raw))

    def from_raw(self, raw: int) -> float:
        return raw * self.scale + self.offset

    def saturates(self, value: float | None) -> bool:
        """Did this value hit a rail? The UI says "18+ kt" rather than "18 kt"."""
        if value is None:
            return False
        numeric = float(value)
        if numeric != numeric or numeric in (float("inf"), float("-inf")):
            return False  # not a reading at all; to_raw will refuse it
        raw = round((numeric - self.offset) / self.scale)
        return raw > self.max_raw or raw < 0


FIELDS: tuple[Field, ...] = (
    Field(
        "msg_type", 4, "message type", "0=advisory 1=alert 2=all-clear 3=test", choices=MSG_TYPES
    ),
    Field("schema_ver", 3, "schema version", "integer"),
    Field("issue_slot", 10, "issue time", "15-min slots, 7-day wrap (0-671)", unit="slot"),
    Field("valid_hours", 4, "validity", "hours, 0-15", unit="h"),
    Field("zone_id", 20, "zone cell", "lat_idx * 560 + lon_idx over 6-24N / 66-94E at 0.05 deg"),
    Field("lat_offset", 8, "position in cell, latitude", "0.05/256 ~ 22 m"),
    Field("lon_offset", 8, "position in cell, longitude", "0.05/256 ~ 22 m"),
    Field(
        "risk_class", 2, "risk class", "0=safe 1=caution 2=no-go 3=unknown", choices=RISK_CLASSES
    ),
    Field(
        "hazard_flags", 8, "hazard bitmap", "wave wind squall lightning cyclone current fog tsunami"
    ),
    Field(
        "wave_hs",
        5,
        "significant wave height",
        "0-7.75 m at 0.25 m, saturating",
        scale=0.25,
        unit="m",
    ),
    Field("wind_kt", 6, "wind speed", "0-63 kt, saturating", unit="kt"),
    Field("wind_dir", 4, "wind direction", "16-point compass index", scale=22.5, unit="deg"),
    Field("curr_kt", 5, "current speed", "0-3.1 kt at 0.1 kt", scale=0.1, unit="kt"),
    Field("curr_dir", 4, "current set", "16-point compass index", scale=22.5, unit="deg"),
    Field(
        "sst",
        5,
        "sea surface temperature",
        "18-33.5 C at 0.5 C",
        scale=0.5,
        offset=18.0,
        unit="degC",
    ),
    Field(
        "chl_class",
        2,
        "chlorophyll class",
        "0=low 1=moderate 2=high 3=very high",
        choices=CHL_CLASSES,
    ),
    Field("pfz_bearing", 4, "PFZ bearing", "16-point compass index", scale=22.5, unit="deg"),
    Field("pfz_dist_nm", 6, "PFZ distance", "0-63 nm", unit="nm"),
    Field("pfz_conf", 2, "PFZ confidence", "0-3"),
    Field("bnd_dist_nm", 5, "boundary distance", "0-31 nm", unit="nm"),
    Field("bnd_type", 2, "boundary type", "0=none 1=IMBL 2=MPA 3=closed", choices=BOUNDARY_TYPES),
    Field("bnd_eta_min", 8, "boundary ETA", "0-255 min, drift-projected", unit="min"),
    Field("reason_code", 8, "reason codebook index", "0-255"),
    Field("evidence_hash", 12, "truncated SHA-256 of the evidence bundle", "for audit"),
)

BY_NAME: dict[str, Field] = {f.name: f for f in FIELDS}


def offsets() -> dict[str, int]:
    """Bit offset of every field, MSB-first, recomputed from widths.

    Nothing anywhere hardcodes an offset. Inserting a field shifts everything
    after it automatically, and the encoder and decoder shift together because
    they both read this.
    """
    out: dict[str, int] = {}
    cursor = 0
    for f in FIELDS:
        out[f.name] = cursor
        cursor += f.width
    return out


def total_bits() -> int:
    return sum(f.width for f in FIELDS)


def headroom_bits() -> int:
    return SEGMENT_BITS - total_bits()


def zone_id(lat: float, lon: float) -> int:
    """Grid cell index for a position, clamped to the EEZ box."""
    lat_idx = int((min(max(lat, ZONE_LAT_MIN), ZONE_LAT_MAX - 1e-9) - ZONE_LAT_MIN) / ZONE_STEP)
    lon_idx = int((min(max(lon, ZONE_LON_MIN), ZONE_LON_MAX - 1e-9) - ZONE_LON_MIN) / ZONE_STEP)
    return lat_idx * ZONE_LON_CELLS + lon_idx


def zone_bounds(zid: int) -> tuple[float, float]:
    """South-west corner of a zone cell."""
    lat_idx, lon_idx = divmod(zid, ZONE_LON_CELLS)
    return ZONE_LAT_MIN + lat_idx * ZONE_STEP, ZONE_LON_MIN + lon_idx * ZONE_STEP


def position_to_fields(lat: float, lon: float) -> tuple[int, int, int]:
    """(zone_id, lat_offset, lon_offset) for a position, to about 22 m."""
    zid = zone_id(lat, lon)
    base_lat, base_lon = zone_bounds(zid)
    lat_off = int(min(255, max(0, round((lat - base_lat) / ZONE_STEP * 256))))
    lon_off = int(min(255, max(0, round((lon - base_lon) / ZONE_STEP * 256))))
    return zid, lat_off, lon_off


def fields_to_position(zid: int, lat_off: int, lon_off: int) -> tuple[float, float]:
    base_lat, base_lon = zone_bounds(zid)
    return base_lat + lat_off / 256 * ZONE_STEP, base_lon + lon_off / 256 * ZONE_STEP


def compass_index(bearing_deg: float | None) -> int:
    """Bearing to a 16-point index. The capsule stores bearings only this way, so
    a demo value off this grid shows one number online and another offline."""
    if bearing_deg is None:
        return 0
    return int((bearing_deg % 360.0) / 22.5 + 0.5) % 16


def index_to_bearing(index: int) -> float:
    return (index % 16) * 22.5


def hazard_bitmap(flags: list[str] | tuple[str, ...] | None) -> int:
    """Flag names to a bitmap. Unknown names are ignored rather than shifting the
    others, because a typo must not silently become "tsunami"."""
    if not flags:
        return 0
    value = 0
    for i, name in enumerate(HAZARD_FLAGS):
        if name in flags:
            value |= 1 << (len(HAZARD_FLAGS) - 1 - i)
    return value


def bitmap_hazards(value: int) -> list[str]:
    return [
        name for i, name in enumerate(HAZARD_FLAGS) if value & (1 << (len(HAZARD_FLAGS) - 1 - i))
    ]


def enum_index(choices: tuple[str, ...], name: str | None, default: int = 0) -> int:
    if name is None:
        return default
    try:
        return choices.index(name)
    except ValueError:
        return default


_QUANTISER_DOC: Callable[[Field], str] = lambda f: (  # noqa: E731
    f"{f.min_value:g} to {f.max_value:g} {f.unit}".strip() if f.scale != 1 or f.offset else ""
)


def spec_table() -> str:
    """Render the field table as markdown, so the doc is generated rather than
    maintained alongside the code."""
    off = offsets()
    lines = [
        "| Offset | Width | Field | Encoding | Range |",
        "|---:|---:|---|---|---|",
    ]
    for f in FIELDS:
        lines.append(
            f"| {off[f.name]} | {f.width} | `{f.name}` | {f.encoding} | {_QUANTISER_DOC(f)} |"
        )
    return "\n".join(lines)


assert total_bits() == TOTAL_BITS, f"field table is {total_bits()} bits, expected {TOTAL_BITS}"
assert (1 << BY_NAME["zone_id"].width) >= ZONE_LAT_CELLS * ZONE_LON_CELLS, "zone_id too narrow"
assert ZONE_LON_CELLS == 560, "zone multiplier must match the spec"
