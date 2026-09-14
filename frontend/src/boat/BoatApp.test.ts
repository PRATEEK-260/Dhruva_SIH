// Regression test for a real bug found in review: BoatApp compared
// capsule.risk_class against the uppercase display labels ("NO_GO", "CAUTION",
// "SAFE") instead of the lowercase-with-underscore wire values decode.ts
// actually produces ("no_go", "caution", "safe", "unknown"). Every comparison
// was always false, so a NO-GO capsule rendered no verdict banner, no override
// notice, and never suppressed the PFZ card — the exact failure CLAUDE.md
// names by title: "a favourable fishing zone never renders above an active
// hazard."

import { describe, expect, it } from "vitest";
import { RISK_CLASSES } from "../shared/capsule/fields";
import { verdictOf } from "./BoatApp";

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
