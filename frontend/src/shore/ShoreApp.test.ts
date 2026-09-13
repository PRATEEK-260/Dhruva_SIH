import { describe, expect, it } from "vitest";
import { displayStatus } from "./ShoreApp";

describe("displayStatus", () => {
  it("maps every real risk_class to its display label", () => {
    expect(displayStatus("safe")).toBe("SAFE");
    expect(displayStatus("caution")).toBe("CAUTION");
    expect(displayStatus("no_go")).toBe("NO-GO");
  });

  it("does not crash on an unrecognised value", () => {
    expect(displayStatus("unknown")).toBe("UNKNOWN");
  });
});
