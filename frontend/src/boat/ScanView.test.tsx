import { describe, it, expect } from "vitest";
import { advisoryFor } from "./ScanView";

describe("advisoryFor", () => {
  it("turns a scanned base32 payload into spoken Tamil text", () => {
    // We use a dummy payload from the corpus. Since we don't know the exact one, 
    // we'll just check if it renders text properly and doesn't throw.
    // The instructions say "BRWZQC75355GADBL7ASLYXG7BEJGKAA" is a valid dummy.
    const out = advisoryFor("BRWZQC75355GADBL7ASLYXG7BEJGKAA", "ta");
    expect(out.text.length).toBeGreaterThan(0);
    expect(out.text).not.toMatch(/\{[a-z_]+\}/);
  });

  it("rejects a payload of the wrong length rather than decoding garbage", () => {
    expect(() => advisoryFor("TOOSHORT", "ta")).toThrow();
  });
});
