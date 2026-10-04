import { describe, expect, it } from "vitest";
import { imageCorners } from "./ShoreApp";
import rasterManifest from "../../public/rasters/manifest.json";
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
  image: `/rasters/${name}.png`,
  bounds: [66, 6, 94, 24],
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

describe("imageCorners", () => {
  it("pins the image top-left, top-right, bottom-right, bottom-left", () => {
    expect(imageCorners(layer("sst", "sst.tif"))).toEqual([
      [66, 24],
      [94, 24],
      [94, 6],
      [66, 6],
    ]);
  });

  it("ships an image and bounds for every layer the console styles", () => {
    for (const key of ["sst", "chlorophyll", "wave_height"]) {
      const entry = (rasterManifest as Record<string, { image: string; bounds: number[] }>)[key];
      expect(entry.image).toBe(`/rasters/${key}.png`);
      expect(entry.bounds).toHaveLength(4);
      const [w, s, e, n] = entry.bounds;
      expect(w < e && s < n).toBe(true);
    }
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
