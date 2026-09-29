// The five states a fisherman sees, derived from the capsule alone so the online
// answer and the one decoded at sea can never show different states.
//
// The capsule keeps its 2-bit risk_class (safe, caution, no-go, unknown); the
// fifth state needs no new bits. A no-go carrying a cyclone, lightning or
// tsunami flag came from an absolute override — an official warning — and shows
// as BLOCKED; any other no-go is UNSAFE, a threshold the sea itself crossed.

import type { Capsule } from "./capsule/decode";
import type { Language } from "./capsule/codebook";
// Machine-translated from EN_LABELS by scripts/verdict_labels.py (Bhashini
// IndicTrans2). Needs a native speaker's check before any public claim.
import translated from "./verdict-labels.json";
import reasonsJson from "./verdict-reasons.json";

export type VerdictState = "safe" | "caution" | "unsafe" | "blocked" | "unavailable";

export const VERDICT_STATES: VerdictState[] = ["safe", "caution", "unsafe", "blocked", "unavailable"];

const OFFICIAL_WARNINGS = new Set(["cyclone", "lightning", "tsunami"]);

export function verdictState(capsule: Pick<Capsule, "risk_class" | "hazards">): VerdictState {
  switch (capsule.risk_class) {
    case "safe":
      return "safe";
    case "caution":
      return "caution";
    case "no_go":
      return capsule.hazards.some((h) => OFFICIAL_WARNINGS.has(h)) ? "blocked" : "unsafe";
    default:
      return "unavailable";
  }
}

/** Fishing-zone advice never renders above an active hazard. */
export function suppressesFishing(state: VerdictState): boolean {
  return state === "unsafe" || state === "blocked" || state === "unavailable";
}

export interface Label {
  word: string;
  line: string;
}

// The line is the action, first: what to do, before why. Must match
// scripts/verdict_labels.py, which translates these and speaks them as the
// offline clips.
export const EN_LABELS: Record<VerdictState, Label> = {
  safe: { word: "Safe", line: "You can go to sea." },
  caution: { word: "Caution", line: "Go only with care." },
  unsafe: { word: "Unsafe", line: "Do not go to sea." },
  blocked: { word: "Blocked", line: "Do not go to sea. An official warning is active." },
  unavailable: { word: "No data", line: "Check the official warning before you go." },
};

// _source records the English each line was translated from; it is not a language.
const LABELS = translated as unknown as Partial<Record<string, Record<VerdictState, Label>>>;

export function verdictLabel(state: VerdictState, lang: Language): Label {
  return LABELS[lang]?.[state] ?? EN_LABELS[state];
}

// ---------------------------------------------------------------- reasons ----
// One short reason, with no numbers. The figures are spoken, and shown only
// under "Show evidence". Worked out from the capsule's own hazard flags, so a
// satellite message gets the same reason as an online answer.

export type ReasonKey =
  | "safe"
  | "caution_wave"
  | "caution_wind"
  | "caution_alert"
  | "unsafe_wave"
  | "unsafe_wind"
  | "blocked_cyclone"
  | "blocked_lightning"
  | "blocked_tsunami"
  | "unavailable";

export const EN_REASONS: Record<ReasonKey, string> = {
  safe: "Waves and wind are within your boat's limits.",
  caution_wave: "The waves are near your boat's limit.",
  caution_wind: "The wind is near your boat's limit.",
  caution_alert: "A warning is out that could not be checked.",
  unsafe_wave: "The waves are too high for your boat.",
  unsafe_wind: "The wind is too strong for your boat.",
  blocked_cyclone: "A cyclone warning is active near you.",
  blocked_lightning: "Lightning is reported near you.",
  blocked_tsunami: "A tsunami alert is in force.",
  unavailable: "The sea could not be checked.",
};

export function reasonKey(capsule: Pick<Capsule, "risk_class" | "hazards">): ReasonKey {
  const h = new Set(capsule.hazards);
  switch (verdictState(capsule)) {
    case "safe":
      return "safe";
    case "caution":
      return h.has("wave") ? "caution_wave" : h.has("wind") ? "caution_wind" : "caution_alert";
    case "unsafe":
      return h.has("wind") && !h.has("wave") ? "unsafe_wind" : "unsafe_wave";
    case "blocked":
      return h.has("tsunami") ? "blocked_tsunami" : h.has("cyclone") ? "blocked_cyclone" : "blocked_lightning";
    default:
      return "unavailable";
  }
}

const REASONS = reasonsJson as Partial<Record<string, Partial<Record<ReasonKey, string>>>>;

export function verdictReason(capsule: Pick<Capsule, "risk_class" | "hazards">, lang: Language): string {
  const k = reasonKey(capsule);
  return REASONS[lang]?.[k] ?? EN_REASONS[k];
}
