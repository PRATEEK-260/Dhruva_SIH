// The one-tap questions. Each has a one-byte code so that, at sea, the question
// can go up the boat terminal's short-message link as a single byte while the
// answer comes back as a 145-bit capsule. Every one routes to a node set that
// answers it today; questions the system cannot answer yet are not offered.

import type { Language } from "./capsule/codebook";
import questionList from "./questions.json";

export type Departure = "now" | "tomorrow5" | "tomorrow7";

export interface Question {
  code: number;
  // No departure here: the question never names a time. The Leaving selector
  // decides when, so a question and the selector cannot disagree.
  text: Partial<Record<Language, string>> & { en: string };
}

// The list lives in questions.json so scripts/record_demo.py records exactly
// the questions the phone offers.
export const QUESTIONS = questionList as Question[];

export function questionText(q: Question, lang: Language): string {
  return q.text[lang] ?? q.text.en;
}

export function questionByCode(code: number): Question | undefined {
  return QUESTIONS.find((q) => q.code === code);
}

/** The instant a departure refers to, as UTC ISO, or undefined for now. Times are
 * India Standard Time, which has no daylight saving: UTC+05:30 all year. */
export function departureTime(d: Departure, from: Date = new Date()): string | undefined {
  if (d === "now") return undefined;
  const hour = d === "tomorrow5" ? 5 : 7;
  const ist = new Date(from.getTime() + 330 * 60_000);
  const utc = Date.UTC(ist.getUTCFullYear(), ist.getUTCMonth(), ist.getUTCDate() + 1, hour, 0) - 330 * 60_000;
  return new Date(utc).toISOString();
}

export const DEPARTURE_LABEL: Record<Departure, string> = {
  now: "Now",
  tomorrow5: "Tomorrow 5 AM",
  tomorrow7: "Tomorrow 7 AM",
};

// ---------------------------------------------------------------- uplink ----
// Phone to boat terminal, shown as a QR because this demo has no Bluetooth link.
// "DQ" + code + language, e.g. "DQ1TA". Five characters; the satellite hop
// carries only the code byte and the language.

export function uplinkPayload(code: number, lang: Language): string {
  return `DQ${code}${lang.toUpperCase()}`;
}

export function parseUplink(text: string): { code: number; lang: Language } | null {
  const m = /^DQ(\d)([A-Z]{2,3})$/.exec(text.trim());
  if (!m) return null;
  return { code: Number(m[1]), lang: m[2].toLowerCase() as Language };
}
