import { describe, expect, it } from "vitest";
import { QUESTIONS, SATELLITE_QUESTIONS } from "./questions";

describe("questions", () => {
  it("never offers an online-only question to the boat terminal", () => {
    // Query #7's answer is a baseline comparison the 145-bit capsule cannot carry.
    expect(SATELLITE_QUESTIONS.some((q) => q.online_only)).toBe(false);
    expect(SATELLITE_QUESTIONS.map((q) => q.code)).not.toContain(7);
  });

  it("asks query #7 in every pilot language", () => {
    const q = QUESTIONS.find((x) => x.code === 7);
    expect(q?.online_only).toBe(true);
    for (const lang of ["en", "ta", "ml", "or", "hi"] as const) expect(q?.text[lang]).toBeTruthy();
  });

  it("keeps question codes unique and one digit, as the uplink carries them", () => {
    const codes = QUESTIONS.map((q) => q.code);
    expect(new Set(codes).size).toBe(codes.length);
    for (const c of codes) {
      expect(c).toBeGreaterThanOrEqual(0);
      expect(c).toBeLessThanOrEqual(9);
    }
  });
});
