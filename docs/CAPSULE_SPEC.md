# Capsule specification

**Generated from `backend/dhruva/codec/fields.py`. Do not edit by hand** — that
file is the single source of truth, and the encoder, the decoder and this table
are all derived from it so they cannot drift apart.

Total **145 bits** (19 bytes) inside a 220-bit
NavIC L5 segment, leaving **75 bits** free. Reserved
use for the free bits: a 4-waypoint return route at reduced precision when
`risk_class` is no-go.

Bit order is MSB-first. Offsets below are computed from the widths; nothing in
the codebase hardcodes one.

## Fields

| Offset | Width | Field | Encoding | Range |
|---:|---:|---|---|---|
| 0 | 4 | `msg_type` | 0=advisory 1=alert 2=all-clear 3=test |  |
| 4 | 3 | `schema_ver` | integer |  |
| 7 | 10 | `issue_slot` | 15-min slots, 7-day wrap (0-671) |  |
| 17 | 4 | `valid_hours` | hours, 0-15 |  |
| 21 | 20 | `zone_id` | lat_idx * 560 + lon_idx over 6-24N / 66-94E at 0.05 deg |  |
| 41 | 8 | `lat_offset` | 0.05/256 ~ 22 m |  |
| 49 | 8 | `lon_offset` | 0.05/256 ~ 22 m |  |
| 57 | 2 | `risk_class` | 0=safe 1=caution 2=no-go 3=unknown |  |
| 59 | 8 | `hazard_flags` | wave wind squall lightning cyclone current fog tsunami |  |
| 67 | 5 | `wave_hs` | 0-7.75 m at 0.25 m, saturating | 0 to 7.75 m |
| 72 | 6 | `wind_kt` | 0-63 kt, saturating |  |
| 78 | 4 | `wind_dir` | 16-point compass index | 0 to 337.5 deg |
| 82 | 5 | `curr_kt` | 0-3.1 kt at 0.1 kt | 0 to 3.1 kt |
| 87 | 4 | `curr_dir` | 16-point compass index | 0 to 337.5 deg |
| 91 | 5 | `sst` | 18-33.5 C at 0.5 C | 18 to 33.5 degC |
| 96 | 2 | `chl_class` | 0=low 1=moderate 2=high 3=very high |  |
| 98 | 4 | `pfz_bearing` | 16-point compass index | 0 to 337.5 deg |
| 102 | 6 | `pfz_dist_nm` | 0-63 nm |  |
| 108 | 2 | `pfz_conf` | 0-3 |  |
| 110 | 5 | `bnd_dist_nm` | 0-31 nm |  |
| 115 | 2 | `bnd_type` | 0=none 1=IMBL 2=MPA 3=closed |  |
| 117 | 8 | `bnd_eta_min` | 0-255 min, drift-projected |  |
| 125 | 8 | `reason_code` | 0-255 |  |
| 133 | 12 | `evidence_hash` | for audit |  |

## Rules

**Every quantiser clamps.** A value past the top of a scale saturates at the top,
which reads as "at least this bad". Wrapping would turn a 9 m sea into a calm
one, and a crew acts on calm. This is enforced once, in `Field.to_raw`, rather
than trusted to each field. `saturating_fields()` reports which values hit a rail
so the interface can show "18+ kt" rather than presenting a rail as exact.

**The decoder is pure.** No network, no filesystem, no clock. The whole claim is
that a phone with its radio off expands a capsule into a spoken advisory; a
decoder that reaches for anything breaks that on the day it matters. A test
asserts the module imports nothing that needs the world.

**Figures are quantised, not rounded for display.** Wave to 0.25 m, SST to 0.5 C,
current to 0.1 kt, every bearing to the 16-point compass. A demo value off that
grid shows one number online and a different one offline, on screen, in front of
whoever is watching.

## Transports

One wire format, three carriers, identical bits on each — the NavIC claim is
segment conformance, and conformance is arithmetic that does not care which pipe
the bytes arrived down.

| Carrier | Format | Size |
|---|---|---|
| QR | base32, unpadded uppercase | 31 characters |
| SMS | hex | 38 characters |
| Bluetooth | raw | 19 bytes |

Base32 rather than base64 for QR: alphanumeric mode covers A–Z and 0–9, so an
uppercase base32 string encodes more densely and scanners misread fewer
characters than with mixed-case base64.
