import { describe, expect, it } from "vitest";
import { suppressesFishing, verdictLabel, verdictState } from "./verdict";
import { bearingDeg, distanceKm, wayHome } from "./harbour";
import { departureTime, parseUplink, uplinkPayload } from "./questions";

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
