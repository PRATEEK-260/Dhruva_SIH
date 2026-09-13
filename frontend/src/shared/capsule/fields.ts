// Ported from backend/dhruva/codec/fields.py — the field table is the single
// source of truth there; this file must be kept in step with it by hand, and
// eval/capsule_corpus.jsonl (500 capsules with expected hex/base32, exercised
// by decode.test.ts) is what proves the two have not drifted apart. Widths,
// order, scale and offset are copied verbatim; anything not needed to DECODE a
// capsule (to_raw / encoding) is left out, since the phone only ever decodes.

export const TOTAL_BITS = 145;
export const SEGMENT_BITS = 220;
export const CAPSULE_BYTES = Math.ceil(TOTAL_BITS / 8); // 19

// Zone grid: the Indian EEZ box at 0.05 degrees.
export const ZONE_LAT_MIN = 6.0;
export const ZONE_LAT_MAX = 24.0;
export const ZONE_LON_MIN = 66.0;
export const ZONE_LON_MAX = 94.0;
export const ZONE_STEP = 0.05;
export const ZONE_LON_CELLS = Math.round((ZONE_LON_MAX - ZONE_LON_MIN) / ZONE_STEP); // 560

export const HAZARD_FLAGS = [
  "wave",
  "wind",
  "squall",
  "lightning",
  "cyclone",
  "current",
  "fog",
  "tsunami",
] as const;

export const MSG_TYPES = ["advisory", "alert", "all_clear", "test"] as const;
export const RISK_CLASSES = ["safe", "caution", "no_go", "unknown"] as const;
export const BOUNDARY_TYPES = ["none", "imbl", "mpa", "closed"] as const;
export const CHL_CLASSES = ["low", "moderate", "high", "very_high"] as const;

export interface FieldSpec {
  name: string;
  width: number;
  /** raw = (value - offset) / scale; value = raw * scale + offset. */
  scale: number;
  offset: number;
}

/** MSB-first, in exactly this order — offsets are never written down, they are
 * always the running sum of the widths before a field, on both sides of the
 * wire, so a reordering here breaks both languages identically rather than
 * silently disagreeing. */
export const FIELDS: readonly FieldSpec[] = [
  { name: "msg_type", width: 4, scale: 1, offset: 0 },
  { name: "schema_ver", width: 3, scale: 1, offset: 0 },
  { name: "issue_slot", width: 10, scale: 1, offset: 0 },
  { name: "valid_hours", width: 4, scale: 1, offset: 0 },
  { name: "zone_id", width: 20, scale: 1, offset: 0 },
  { name: "lat_offset", width: 8, scale: 1, offset: 0 },
  { name: "lon_offset", width: 8, scale: 1, offset: 0 },
  { name: "risk_class", width: 2, scale: 1, offset: 0 },
  { name: "hazard_flags", width: 8, scale: 1, offset: 0 },
  { name: "wave_hs", width: 5, scale: 0.25, offset: 0 },
  { name: "wind_kt", width: 6, scale: 1, offset: 0 },
  { name: "wind_dir", width: 4, scale: 22.5, offset: 0 },
  { name: "curr_kt", width: 5, scale: 0.1, offset: 0 },
  { name: "curr_dir", width: 4, scale: 22.5, offset: 0 },
  { name: "sst", width: 5, scale: 0.5, offset: 18.0 },
  { name: "chl_class", width: 2, scale: 1, offset: 0 },
  { name: "pfz_bearing", width: 4, scale: 22.5, offset: 0 },
  { name: "pfz_dist_nm", width: 6, scale: 1, offset: 0 },
  { name: "pfz_conf", width: 2, scale: 1, offset: 0 },
  { name: "bnd_dist_nm", width: 5, scale: 1, offset: 0 },
  { name: "bnd_type", width: 2, scale: 1, offset: 0 },
  { name: "bnd_eta_min", width: 8, scale: 1, offset: 0 },
  { name: "reason_code", width: 8, scale: 1, offset: 0 },
  { name: "evidence_hash", width: 12, scale: 1, offset: 0 },
];

const WIDTH_SUM = FIELDS.reduce((sum, f) => sum + f.width, 0);
if (WIDTH_SUM !== TOTAL_BITS) {
  throw new Error(`fields.ts: field widths sum to ${WIDTH_SUM}, expected ${TOTAL_BITS}`);
}

export const BY_NAME: ReadonlyMap<string, FieldSpec> = new Map(FIELDS.map((f) => [f.name, f]));

export function fromRaw(name: string, raw: number): number {
  const f = BY_NAME.get(name);
  if (!f) throw new Error(`unknown field ${name}`);
  return raw * f.scale + f.offset;
}
