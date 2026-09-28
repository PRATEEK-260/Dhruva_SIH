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

export const EN_LABELS: Record<VerdictState, Label> = {
  safe: { word: "Safe", line: "Conditions are within the limits for your boat." },
  caution: { word: "Caution", line: "Conditions are near the limit for your boat. Take care." },
  unsafe: { word: "Unsafe", line: "Do not go to sea. The sea is too rough for your boat." },
  blocked: { word: "Blocked", line: "Do not go to sea. An official warning is active." },
  unavailable: {
    word: "No data",
    line: "The sea could not be checked. Follow the official warning.",
  },
};

const LABELS = translated as Partial<Record<string, Record<VerdictState, Label>>>;

export function verdictLabel(state: VerdictState, lang: Language): Label {
  return LABELS[lang]?.[state] ?? EN_LABELS[state];
}
