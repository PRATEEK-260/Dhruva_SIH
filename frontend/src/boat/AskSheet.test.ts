// Coverage rehomed. These assertions used to live in BoatApp.test.ts against an
// askAdvisory() that the boat/emulator split deleted, leaving the test importing
// a function that no longer existed — tsc had been failing on it. The flow now
// belongs to AskSheet, so the tests follow it here rather than being dropped.

import { afterEach, describe, expect, it, vi } from "vitest";
import { askAdvisory } from "./AskSheet";

// A capsule that genuinely encodes risk_class "caution" and wind 22 kt, so the
// fixture's JSON fields and its capsule bits agree. The fixture inherited from
// BoatApp.test.ts did not: it claimed "caution" alongside a capsule that decodes
// to "unknown" at 3.0 m. That mattered, because the card renders from the
// DECODED capsule, not from the JSON string — an asked answer and a scanned one
// have to be the same object by the time they reach the screen.
const CAPSULE = "ALILA3YDQAACQBS2RCLUAAAAAKAAAAA";

afterEach(() => {
  vi.unstubAllGlobals();
});

function stubOk(body: Record<string, unknown>) {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => body }));
}

const RESPONSE = {
  narration: "Take care. Wind 22 knots, near the limit for your boat.",
  risk_class: "caution",
  firewall_passed: true,
  evidence: {},
  capsule_base32: CAPSULE,
  reason_code: 0b01_010_000,
  notice: "Advisory only. Follow official INCOIS and IMD warnings.",
};

describe("askAdvisory", () => {
  it("returns narration and a QR-ready capsule on success", async () => {
    stubOk(RESPONSE);
    const result = await askAdvisory("can I go out?", "ta", "frp_under_12m", 11.05, 79.95);
    expect(result.narration).toBe(RESPONSE.narration);
    expect(result.riskClass).toBe("caution");
    expect(result.capsuleBase32).toBe(CAPSULE);
  });

  it("decodes the capsule so an asked answer renders through the offline path", async () => {
    // The point of returning capsule_base32 at all: an asked advisory and a
    // scanned one must be the same object by the time they reach the card.
    stubOk(RESPONSE);
    const result = await askAdvisory("can I go out?", "en", "frp_under_12m", 11.05, 79.95);
    expect(result.capsule.risk_class).toBe("caution");
    expect(result.capsule.wind_kt).toBe(22);
  });

  it("sends the position and language the caller asked for", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => RESPONSE });
    vi.stubGlobal("fetch", fetchMock);
    await askAdvisory("q", "ta", "frp_under_12m", 11.05, 79.95);
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string);
    expect(body).toMatchObject({ lat: 11.05, lon: 79.95, language: "ta" });
  });

  it("throws a clear, catchable error on a network failure", async () => {
    // A boat losing signal mid-question must surface the failure, not fall back
    // to stale data — that is how a crew ends up acting on yesterday's sea.
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(askAdvisory("x", "en", "frp_under_12m", 11.05, 79.95)).rejects.toThrow();
  });

  it("throws on a non-2xx response rather than returning an empty advisory", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, status: 503 }));
    await expect(askAdvisory("x", "en", "frp_under_12m", 11.05, 79.95)).rejects.toThrow();
  });
});
