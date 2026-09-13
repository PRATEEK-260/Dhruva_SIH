import { afterEach, describe, expect, it, vi } from "vitest";
import { fetchGeoLayer, fetchRecentAdvisories, postAdvisory } from "./client";

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("postAdvisory", () => {
  it("posts to /api/advisory and returns the parsed response", async () => {
    const mockResponse = {
      narration: "Conditions are within limits.",
      risk_class: "safe",
      firewall_passed: true,
      evidence: {},
      capsule_base32: "BRWZQC75355GADBL7ASLYXG7BEJGKAA",
      reason_code: 0,
      notice: "Advisory only. Follow official INCOIS and IMD warnings.",
    };
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => mockResponse,
    });
    vi.stubGlobal("fetch", fetchMock);

    const result = await postAdvisory({ query: "can I go out?", lat: 11.05, lon: 79.95 });

    expect(result).toEqual(mockResponse);
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/advisory",
      expect.objectContaining({ method: "POST" }),
    );
  });

  it("throws with a clear message on a network failure", async () => {
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new TypeError("Failed to fetch")));
    await expect(postAdvisory({ query: "x", lat: 0, lon: 0 })).rejects.toThrow();
  });

  it("throws on a non-OK response rather than returning a half-filled object", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn().mockResolvedValue({ ok: false, status: 422, json: async () => ({}) }),
    );
    await expect(postAdvisory({ query: "x", lat: 0, lon: 0 })).rejects.toThrow();
  });
});

describe("fetchRecentAdvisories", () => {
  it("fetches /api/advisory/recent", async () => {
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => [] });
    vi.stubGlobal("fetch", fetchMock);
    await fetchRecentAdvisories(10);
    expect(fetchMock).toHaveBeenCalledWith("/api/advisory/recent?limit=10");
  });
});

describe("fetchGeoLayer", () => {
  it("fetches the named layer", async () => {
    const fc = { type: "FeatureCollection", features: [] };
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => fc });
    vi.stubGlobal("fetch", fetchMock);
    const result = await fetchGeoLayer("boundaries");
    expect(fetchMock).toHaveBeenCalledWith("/api/geo/boundaries");
    expect(result).toEqual(fc);
  });
});
