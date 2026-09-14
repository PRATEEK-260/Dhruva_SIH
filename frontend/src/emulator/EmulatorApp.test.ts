// Coverage rehomed. generateHandoffQr moved from BoatApp into the emulator
// during the boat/emulator split but stayed private, so BoatApp.test.ts was left
// importing a name that no longer existed anywhere. The QR is the offline
// handoff — if it stops being deterministic or stops distinguishing capsules,
// the airplane-mode demo silently shows the wrong advisory.

import { describe, expect, it } from "vitest";
import { generateHandoffQr } from "./EmulatorApp";

const CAPSULE = "BRWZQC75355GADBL7ASLYXG7BEJGKAA";
const OTHER = "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA";

describe("generateHandoffQr", () => {
  it("produces a non-empty SVG string", async () => {
    expect(await generateHandoffQr(CAPSULE)).toContain("<svg");
  });

  it("is deterministic for the same capsule", async () => {
    expect(await generateHandoffQr(CAPSULE)).toBe(await generateHandoffQr(CAPSULE));
  });

  it("differs for a different capsule", async () => {
    expect(await generateHandoffQr(CAPSULE)).not.toBe(await generateHandoffQr(OTHER));
  });
});
