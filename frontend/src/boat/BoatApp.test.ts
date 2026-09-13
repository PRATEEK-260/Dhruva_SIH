// Regression test for a real bug found in review: BoatApp compared
// capsule.risk_class against the uppercase display labels ("NO_GO", "CAUTION",
// "SAFE") instead of the lowercase-with-underscore wire values decode.ts
// actually produces ("no_go", "caution", "safe", "unknown"). Every comparison
// was always false, so a NO-GO capsule rendered no verdict banner, no override
// notice, and never suppressed the PFZ card — the exact failure CLAUDE.md
// names by title: "a favourable fishing zone never renders above an active
// hazard."

import { afterEach, describe, expect, it, vi } from "vitest";
import { RISK_CLASSES } from "../shared/capsule/fields";
import { askAdvisory, generateHandoffQr, verdictOf } from "./BoatApp";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("verdictOf", () => {
  it("recognises every real wire value RISK_CLASSES can produce", () => {
    // RISK_CLASSES = ["safe", "caution", "no_go", "unknown"] — "unknown" has
    // no banner of its own (falls through to the "no data yet" UI state), so
    // it alone is expected to map to null.
    for (const riskClass of RISK_CLASSES) {
      const result = verdictOf(riskClass);
      if (riskClass === "unknown") {
        expect(result).toBeNull();
      } else {
        expect(result).toBe(riskClass);
      }
    }
  });

  it("does not recognise the uppercase display labels", () => {
    // This is the specific regression: these must NOT match, because they are
    // never what a decoded capsule actually contains.
    for (const wrong of ["NO_GO", "CAUTION", "SAFE", "NO-GO"] as const) {
      expect(verdictOf(wrong as never)).toBeNull();
    }
  });

  it("returns null for an absent capsule", () => {
    expect(verdictOf(undefined)).toBeNull();
  });
});

describe("askAdvisory", () => {
  it("returns narration and a QR-ready capsule on success", async () => {
    const mockResponse = {
      narration: "Take care. Wind 22 knots, near the limit for your boat.",
      risk_class: "caution",
      firewall_passed: true,
      evidence: {},
      capsule_base32: "BRWZQC75355GADBL7ASLYXG7BEJGKAA",
      reason_code: 0b01_010_000,
      notice: "Advisory only. Follow official INCOIS and IMD warnings.",
    };
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: true, json: async () => mockResponse }),
    );

    const result = await askAdvisory("can I go out?", "ta", "frp_under_12m");

    expect(result.narration).toBe(mockResponse.narration);
    expect(result.riskClass).toBe("caution");
    expect(result.capsuleBase32).toBe(mockResponse.capsule_base32);
  });

  it("throws a clear, catchable error on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(askAdvisory("x", "en", "frp_under_12m")).rejects.toThrow();
  });
});

describe("generateHandoffQr", () => {
  it("produces a non-empty SVG string", async () => {
    const svg = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    expect(svg).toContain("<svg");
  });

  it("is deterministic for the same capsule", async () => {
    const a = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    const b = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    expect(a).toBe(b);
  });

  it("differs for a different capsule", async () => {
    const a = await generateHandoffQr("BRWZQC75355GADBL7ASLYXG7BEJGKAA");
    const b = await generateHandoffQr("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA");
    expect(a).not.toBe(b);
  });
});
