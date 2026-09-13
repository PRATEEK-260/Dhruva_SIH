// The codebook renderer — ported from backend/dhruva/codec/codebook.py's
// decode_reason() and render(). Turns a decoded Capsule into the sentence a
// phone speaks, entirely from data baked into the bundle at build time: no
// network, no filesystem, at runtime — matching decode.ts's own purity
// requirement, since this is the layer that actually produces the spoken
// advisory.
//
// Each data/codebook/build/<lang>.json is imported statically so the bundler
// inlines it; the alternative (fetching it) would make the offline claim false.

import { RISK_CLASSES } from "./fields";
import type { Capsule } from "./decode";

import en from "../../../../data/codebook/build/en.json";
import ta from "../../../../data/codebook/build/ta.json";
import te from "../../../../data/codebook/build/te.json";
import ml from "../../../../data/codebook/build/ml.json";
import kn from "../../../../data/codebook/build/kn.json";
import mr from "../../../../data/codebook/build/mr.json";
import kok from "../../../../data/codebook/build/kok.json";
import gu from "../../../../data/codebook/build/gu.json";
import or from "../../../../data/codebook/build/or.json";
import bn from "../../../../data/codebook/build/bn.json";
import hi from "../../../../data/codebook/build/hi.json";
import ur from "../../../../data/codebook/build/ur.json";

export const LANGUAGES = [
  "en",
  "ta",
  "te",
  "ml",
  "kn",
  "mr",
  "kok",
  "gu",
  "or",
  "bn",
  "hi",
  "ur",
] as const;
export type Language = (typeof LANGUAGES)[number];

interface CodebookLexicon {
  compass: Record<string, string>;
  bnd_type: Record<string, string>;
  chl_class: Record<string, string>;
  msg_type: Record<string, string>;
  units: Record<string, string>;
  notice: string;
  language: string;
}

interface CodebookDoc {
  version: number;
  language: string;
  notice: string;
  reachable: string[];
  entries: Record<string, string>;
  lexicon: CodebookLexicon;
}

const CODEBOOKS: Record<Language, CodebookDoc> = {
  en,
  ta,
  te,
  ml,
  kn,
  mr,
  kok,
  gu,
  or,
  bn,
  hi,
  ur,
};

// The band value IS the index into RISK_CLASSES — same array decode.ts already
// exports, so this cannot drift from decode.ts's own understanding of the wire
// format.
const BAND_OF: Readonly<Record<string, number>> = Object.fromEntries(
  RISK_CLASSES.map((name, i) => [name, i]),
);

// risk/rules.py's _SEVERITY, NOT the band index order — UNKNOWN sits between
// SAFE and CAUTION, which is exactly why this needs its own table rather than
// reusing band numbers as severity.
const SEVERITY_BY_RISK_CLASS: Readonly<Record<string, number>> = {
  safe: 0,
  unknown: 1,
  caution: 2,
  no_go: 3,
};

function severityOfBand(band: number): number {
  return SEVERITY_BY_RISK_CLASS[RISK_CLASSES[band]];
}

function entryKey(band: number, family: number, modifier: number): string {
  return `b${band}f${family}m${modifier}`;
}

export function splitReason(code: number): [band: number, family: number, modifier: number] {
  if (!Number.isInteger(code) || code < 0 || code > 255) {
    throw new Error(`reason_code must fit one byte, got ${code}`);
  }
  return [(code >> 6) & 0b11, (code >> 3) & 0b111, code & 0b111];
}

export interface ReasonRender {
  band: number;
  family: number;
  modifier: number;
  degraded: boolean;
  text: string;
}

/** Expand the byte, cross-checking it against the capsule's other copy of the
 * verdict (risk_class, 68 bits earlier on the wire). Mirrors codebook.py's
 * decode_reason exactly: coherent+reachable renders as-is; a band mismatch
 * takes the MORE SEVERE of the two and renders that band's generic entry
 * (family/modifier discarded — if the band bits are corrupt the rest may be
 * too); a coherent-but-unreachable code also falls back to the band generic. */
export function decodeReason(
  code: number,
  riskClassIndex: number,
  language: Language,
): ReasonRender {
  const doc = CODEBOOKS[language];
  let [band, family, modifier] = splitReason(code);
  let degraded = false;

  if (band !== riskClassIndex) {
    band = severityOfBand(band) >= severityOfBand(riskClassIndex) ? band : riskClassIndex;
    family = 0;
    modifier = 0;
    degraded = true;
  } else if (!doc.reachable.includes(entryKey(band, family, modifier))) {
    family = 0;
    modifier = 0;
    degraded = true;
  }

  return { band, family, modifier, degraded, text: doc.entries[entryKey(band, family, modifier)] };
}

// ------------------------------------------------------------------ slots ----
// Slots bind to decoded Capsule attributes, NEVER to wire field names — same
// rule codebook.py enforces. A slot is the only way a number reaches a
// sentence, which is what makes the codebook firewall-clean by construction.

const DIRECT_SLOTS = new Set([
  "wave_hs_m",
  "wind_kt",
  "curr_kt",
  "sst_c",
  "pfz_dist_nm",
  "bnd_dist_nm",
  "bnd_eta_min",
  "valid_hours",
]);

// Same factors as codebook.py's CONVERTED_SLOTS, which itself matches
// evidence/firewall.py's DECLARED_CONVERSIONS — three places this constant now
// lives, none of them free to disagree (backend has its own pinning test).
const CONVERTED_SLOTS: Record<string, [source: string, factor: number]> = {
  wave_hs_ft: ["wave_hs_m", 3.280839895],
  wind_kmh: ["wind_kt", 1.852],
};

const LEXICON_SLOTS: Record<string, [source: string, table: string]> = {
  wind_dir_name: ["wind_dir_deg", "compass"],
  curr_dir_name: ["curr_dir_deg", "compass"],
  pfz_bearing_name: ["pfz_bearing_deg", "compass"],
  bnd_type_name: ["bnd_type", "bnd_type"],
  chl_class_name: ["chl_class", "chl_class"],
  msg_type_name: ["msg_type", "msg_type"],
};

const SLOT_RE = /\{([a-z_]+)\}/g;

/** Matches Python's f"{round(value, 2):g}" for every value range this project
 * quantises to (always far under %g's 6-significant-figure threshold): round
 * to 2 decimals, then trim a trailing zero/dot so 3.0 reads "3", not "3.00" —
 * the online and offline cards must show the same digits. */
function formatNumber(value: number): string {
  const rounded = Math.round(value * 100) / 100;
  if (Number.isInteger(rounded)) return String(rounded);
  let text = rounded.toFixed(2);
  if (text.endsWith("0")) text = text.slice(0, -1);
  if (text.endsWith(".")) text = text.slice(0, -1);
  return text;
}

function compassName(degrees: number, lexicon: CodebookLexicon): string {
  const index = Math.round(degrees / 22.5) % 16;
  return lexicon.compass[String(index)];
}

function capsuleField(capsule: Capsule, name: string): unknown {
  return (capsule as unknown as Record<string, unknown>)[name];
}

/** Substitute every {slot} in a template. Throws on an unknown slot rather
 * than leaving it visible in a spoken sentence. */
export function fill(template: string, capsule: Capsule, lexicon: CodebookLexicon): string {
  return template.replace(SLOT_RE, (_match, name: string) => {
    if (DIRECT_SLOTS.has(name)) {
      return formatNumber(capsuleField(capsule, name) as number);
    }
    if (name in CONVERTED_SLOTS) {
      const [source, factor] = CONVERTED_SLOTS[name];
      return formatNumber((capsuleField(capsule, source) as number) * factor);
    }
    if (name in LEXICON_SLOTS) {
      const [source, table] = LEXICON_SLOTS[name];
      const raw = capsuleField(capsule, source);
      if (table === "compass") return compassName(raw as number, lexicon);
      return (lexicon as unknown as Record<string, Record<string, string>>)[table][raw as string];
    }
    throw new Error(`unknown slot {${name}}`);
  });
}

/** The whole offline path: capsule in, spoken sentence out. */
export function renderReason(
  capsule: Capsule,
  language: Language,
): { text: string; degraded: boolean } {
  const riskClassIndex = BAND_OF[capsule.risk_class];
  const chosen = decodeReason(capsule.reason_code, riskClassIndex, language);
  return { text: fill(chosen.text, capsule, CODEBOOKS[language].lexicon), degraded: chosen.degraded };
}
