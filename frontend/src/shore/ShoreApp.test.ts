import { describe, expect, it } from "vitest";
import { tilejsonUrl } from "./ShoreApp";
import { ageLabel, displayStatus, filterRequests, inCapsuleGrid } from "./status";
import { asBundle, utcStamp } from "./InspectPanel";
import type { AdvisoryLogEntry, RasterLayer } from "../shared/api/client";

const layer = (name: string, file: string): RasterLayer => ({
  layer: name,
  file,
  dataset_id: "cmems_test",
  variable: "v",
  unit: "",
  valid_time: null,
  generated_at: "2026-09-14T00:00:00Z",
});

const entry = (id: number, risk_class: string): AdvisoryLogEntry => ({
  id, risk_class, boat_class: "frp_under_12m", lat: 11.05, lon: 79.95, issued_at: "2026-09-14T00:00:00Z", valid_for: null,
});

describe("displayStatus", () => {
  it("maps every real risk_class to its display label", () => {
    expect(displayStatus("safe")).toBe("SAFE");
    expect(displayStatus("caution")).toBe("CAUTION");
    expect(displayStatus("no_go")).toBe("NO-GO");
  });

  it("does not crash on an unrecognised value", () => {
    expect(displayStatus("unknown")).toBe("UNKNOWN");
    expect(displayStatus("NO-GO")).toBe("UNKNOWN");
  });
});

describe("tilejsonUrl", () => {
  it("builds the SST layer URL with its rescale and colormap", () => {
    const url = tilejsonUrl(layer("sst", "sst.tif"));
    expect(url).toContain("/tiles/cog/WebMercatorQuad/tilejson.json");
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fsst.tif");
    expect(url).toContain("rescale=18%2C33");
    expect(url).toContain("colormap_name=thermal");
  });

  it("builds the chlorophyll layer URL with its own rescale and colormap", () => {
    const url = tilejsonUrl(layer("chlorophyll", "chlorophyll.tif"));
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fchlorophyll.tif");
    expect(url).toContain("rescale=0%2C5");
    expect(url).toContain("colormap_name=algae");
  });

  it("builds the wave-height layer URL with its own rescale and colormap", () => {
    const url = tilejsonUrl(layer("wave_height", "wave_height.tif"));
    expect(url).toContain("url=file%3A%2F%2F%2Fdata%2Fcogs%2Fwave_height.tif");
    expect(url).toContain("rescale=0%2C8");
    expect(url).toContain("colormap_name=blues");
  });
});

describe("filterRequests", () => {
  const entries = [entry(1, "safe"), entry(2, "no_go"), entry(3, "caution"), entry(4, "no_go")];

  it("returns everything for all", () => {
    expect(filterRequests(entries, "all")).toHaveLength(4);
  });

  it("matches the lowercase risk_class, not the display label", () => {
    expect(filterRequests(entries, "no_go").map((e) => e.id)).toEqual([2, 4]);
    expect(filterRequests(entries, "safe").map((e) => e.id)).toEqual([1]);
  });
});

describe("inCapsuleGrid", () => {
  it("accepts the demo coordinate at sea off Tamil Nadu", () => {
    expect(inCapsuleGrid(11.05, 79.95)).toBe(true);
  });

  it("rejects positions the zone grid cannot encode", () => {
    expect(inCapsuleGrid(5.9, 80)).toBe(false);
    expect(inCapsuleGrid(24, 80)).toBe(false);
    expect(inCapsuleGrid(12, 94)).toBe(false);
    expect(inCapsuleGrid(12, 65.9)).toBe(false);
  });
});

describe("ageLabel", () => {
  const now = new Date("2026-09-14T12:00:00Z");
  it("reads recent, minutes and hours", () => {
    expect(ageLabel(new Date("2026-09-14T11:59:30Z"), now)).toBe("just now");
    expect(ageLabel(new Date("2026-09-14T11:48:00Z"), now)).toBe("12 min ago");
    expect(ageLabel(new Date("2026-09-14T09:00:00Z"), now)).toBe("3 h ago");
  });
});

describe("asBundle", () => {
  it("refuses evidence with no items array", () => {
    expect(asBundle({})).toBeNull();
    expect(asBundle({ items: "nope" })).toBeNull();
  });

  it("accepts a real bundle shape", () => {
    expect(asBundle({ items: [], fired_rules: [] })?.items).toEqual([]);
  });
});

describe("utcStamp", () => {
  it("formats to minute precision in UTC", () => {
    expect(utcStamp("2026-09-14T06:30:00+05:30")).toBe("2026-09-14 01:00Z");
  });

  it("shows a dash for missing times", () => {
    expect(utcStamp(null)).toBe("—");
  });
});
