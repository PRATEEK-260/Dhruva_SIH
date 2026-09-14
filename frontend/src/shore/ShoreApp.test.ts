import { describe, expect, it } from "vitest";
import { displayStatus, tilejsonUrl } from "./ShoreApp";

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

describe("tilejsonUrl", () => {
  it("builds the SST layer URL with its rescale and colormap", () => {
    const url = tilejsonUrl("sst");
    expect(url).toContain("/tiles/cog/WebMercatorQuad/tilejson.json");
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fsst.tif");
    expect(url).toContain("rescale=18%2C33");
    expect(url).toContain("colormap_name=thermal");
  });

  it("builds the chlorophyll layer URL with its own rescale and colormap", () => {
    const url = tilejsonUrl("chlorophyll");
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fchlorophyll.tif");
    expect(url).toContain("rescale=0%2C5");
    expect(url).toContain("colormap_name=algae");
  });

  it("builds the wave-height layer URL with its own rescale and colormap", () => {
    const url = tilejsonUrl("wave_height");
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fwave_height.tif");
    expect(url).toContain("rescale=0%2C8");
    expect(url).toContain("colormap_name=blues");
  });
});
