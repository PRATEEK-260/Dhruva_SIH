// The phone's screen text in the pilot languages (shared/ui-strings.json, made
// by scripts/ui_strings.py with Bhashini and checked by hand where it erred).
// Text only: a number on screen always comes from the evidence, never from here.

import type { Language } from "./capsule/codebook";
import strings from "./ui-strings.json";

type Table = Record<string, Record<string, string>>;
const TABLE = strings as unknown as Table;

export type UiKey = keyof typeof strings.en;

/** The string in the language, falling back to English. */
export function t(key: UiKey, lang: Language): string {
  return TABLE[lang]?.[key] ?? TABLE.en[key] ?? key;
}
