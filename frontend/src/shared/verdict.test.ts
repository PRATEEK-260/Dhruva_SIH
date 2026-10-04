import { describe, expect, it } from "vitest";
import { EN_LABELS, EN_REASONS, reasonKey, spokenAnswer, suppressesFishing, verdictLabel, verdictState } from "./verdict";
import { bearingDeg, distanceKm, wayHome } from "./harbour";
import { departureTime, parseUplink, uplinkPayload } from "./questions";
import type { Capsule } from "./capsule/decode";

describe("verdictState", () => {
  it("maps the four wire classes and splits no-go by cause", () => {
    expect(verdictState({ risk_class: "safe", hazards: [] })).toBe("safe");
    expect(verdictState({ risk_class: "caution", hazards: ["wind"] })).toBe("caution");
    expect(verdictState({ risk_class: "no_go", hazards: ["wave"] })).toBe("unsafe");
    expect(verdictState({ risk_class: "no_go", hazards: ["wave", "cyclone"] })).toBe("blocked");
    expect(verdictState({ risk_class: "no_go", hazards: ["tsunami"] })).toBe("blocked");
    expect(verdictState({ risk_class: "unknown", hazards: [] })).toBe("unavailable");
  });

  it("never lets fishing advice show over a hazard or missing data", () => {
    expect(suppressesFishing("safe")).toBe(false);
    expect(suppressesFishing("caution")).toBe(false);
    expect(suppressesFishing("unsafe")).toBe(true);
    expect(suppressesFishing("blocked")).toBe(true);
    expect(suppressesFishing("unavailable")).toBe(true);
  });

  it("falls back to English for a language with no labels", () => {
    expect(verdictLabel("safe", "kok").word).toBe("Safe");
    expect(verdictLabel("safe", "ta").word).not.toBe("Safe");
  });
});

describe("harbour", () => {
  it("measures a degree of latitude as about 111 km due north", () => {
    expect(distanceKm(10, 80, 11, 80)).toBeCloseTo(111.2, 0);
    expect(bearingDeg(10, 80, 11, 80)).toBeCloseTo(0, 5);
    expect(bearingDeg(10, 80, 10, 81)).toBeCloseTo(90, 0);
  });

  it("sends the demo boat south-south-west to Karaikal", () => {
    const home = wayHome(11.05, 79.95, "en");
    expect(home.harbour.name).toBe("Karaikal Port");
    expect(home.km).toBeGreaterThan(20);
    expect(home.km).toBeLessThan(30);
    expect(home.bearing).toBeGreaterThan(180);
    expect(home.bearing).toBeLessThan(225);
  });
});

describe("questions", () => {
  it("round-trips the one-byte uplink", () => {
    expect(parseUplink(uplinkPayload(3, "ta"))).toEqual({ code: 3, lang: "ta" });
    expect(parseUplink("not a question")).toBeNull();
  });

  it("puts tomorrow 5 AM IST at 23:30 UTC today", () => {
    // 28 Sep 2026, 16:00 IST
    const from = new Date("2026-09-28T10:30:00Z");
    expect(departureTime("tomorrow5", from)).toBe("2026-09-28T23:30:00.000Z");
    expect(departureTime("tomorrow7", from)).toBe("2026-09-29T01:30:00.000Z");
    expect(departureTime("now", from)).toBeUndefined();
  });
});

describe("action-first wording", () => {
  it("names the reason from the capsule's own hazard flags", () => {
    expect(reasonKey({ risk_class: "safe", hazards: [] })).toBe("safe");
    expect(reasonKey({ risk_class: "caution", hazards: ["wind"] })).toBe("caution_wind");
    expect(reasonKey({ risk_class: "caution", hazards: [] })).toBe("caution_alert");
    expect(reasonKey({ risk_class: "no_go", hazards: ["wave", "wind"] })).toBe("unsafe_wave");
    expect(reasonKey({ risk_class: "no_go", hazards: ["wind"] })).toBe("unsafe_wind");
    expect(reasonKey({ risk_class: "no_go", hazards: ["wave", "cyclone"] })).toBe("blocked_cyclone");
    expect(reasonKey({ risk_class: "no_go", hazards: ["tsunami"] })).toBe("blocked_tsunami");
    expect(reasonKey({ risk_class: "unknown", hazards: [] })).toBe("unavailable");
  });

  it("puts no number on the fisherman's main screen", () => {
    for (const text of [...Object.values(EN_LABELS).map((l) => l.line), ...Object.values(EN_REASONS)]) {
      expect(text).not.toMatch(/\d/);
    }
  });

  it("leads with what to do", () => {
    expect(EN_LABELS.safe.line).toBe("You can go to sea.");
    expect(EN_LABELS.unsafe.line.startsWith("Do not go to sea")).toBe(true);
    expect(EN_LABELS.blocked.line.startsWith("Do not go to sea")).toBe(true);
  });
});

describe("spoken answer", () => {
  it("opens with the same action line as the headline", async () => {
    const { readFileSync } = await import("node:fs");
    const { decodeCapsule } = await import("./capsule/decode");
    const rows = readFileSync("../eval/capsule_corpus.jsonl", "utf8").trim().split("\n").slice(0, 50);
    for (const row of rows) {
      const capsule = decodeCapsule((JSON.parse(row) as { base32: string }).base32);
      for (const lang of ["en", "ta", "hi"] as const) {
        expect(spokenAnswer(capsule, lang).startsWith(verdictLabel(verdictState(capsule), lang).line)).toBe(true);
      }
    }
  });
});


describe("spoken verdict", () => {
  it("speaks no figures in any language: numbers belong under Show evidence", () => {
    const states = [
      { risk_class: "safe", hazards: [] },
      { risk_class: "caution", hazards: ["wave"] },
      { risk_class: "no_go", hazards: ["wave"] },
      { risk_class: "no_go", hazards: ["cyclone"] },
    ] as const;
    for (const lang of ["en", "ta", "ml", "or", "hi"] as const) {
      for (const st of states) {
        // Only the verdict and its hazards decide what is spoken; the 1.25 m sea
        // that used to be read out must not reach the sentence.
        const capsule = { risk_class: st.risk_class, hazards: [...st.hazards], wave_hs_m: 1.25 } as unknown as Capsule;
        expect(spokenAnswer(capsule, lang)).not.toMatch(/\d/);
      }
    }
  });
});

describe("thunderstorm reason", () => {
  it("names a forecast thunderstorm, not an unchecked warning", () => {
    expect(reasonKey({ risk_class: "caution", hazards: ["squall"] })).toBe("caution_thunder");
    expect(reasonKey({ risk_class: "caution", hazards: [] })).toBe("caution_alert");
  });
});
