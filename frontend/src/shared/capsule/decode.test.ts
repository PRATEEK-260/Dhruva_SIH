// The capsule decoder, ported from backend/dhruva/codec/codec.py.
//
// eval/capsule_corpus.jsonl is the cross-language contract: 500 capsules with
// their expected hex and base32, generated once by the Python side
// (backend/tests/test_codec.py::TestCorpusContract pins that the file matches
// that implementation). This suite proves the TypeScript port produces the
// identical decoded Capsule for every one of them.

import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import type { Capsule } from "./decode";
import { decodeCapsule, decodeHex } from "./decode";

interface CorpusCapsule {
  lat: number;
  lon: number;
  [key: string]: unknown;
}

interface CorpusRow {
  id: string;
  capsule: CorpusCapsule;
  hex: string;
  base32: string;
}

const corpus: CorpusRow[] = readFileSync("../eval/capsule_corpus.jsonl", "utf8")
  .trim()
  .split("\n")
  .map((line) => JSON.parse(line));

// lat/lon are quantised to the position grid on the wire (docs/CAPSULE_SPEC.md),
// so decode legitimately returns the QUANTISED position, not the corpus's
// pre-quantisation input — same tolerance as
// backend/tests/test_codec.py::TestCorpusContract and TestRoundTrip.
const ZONE_STEP = 0.05;
const POSITION_TOLERANCE = ZONE_STEP / 256 + 1e-9;

function expectMatchesCorpusCapsule(decoded: Capsule, expected: CorpusCapsule) {
  const { lat, lon, ...expectedRest } = expected;
  const { lat: decodedLat, lon: decodedLon, ...decodedRest } = decoded;
  expect(Math.abs(decodedLat - lat)).toBeLessThan(POSITION_TOLERANCE);
  expect(Math.abs(decodedLon - lon)).toBeLessThan(POSITION_TOLERANCE);
  expect(decodedRest).toEqual(expectedRest);
}

describe("capsule decoder parity with the Python corpus", () => {
  it("has the full 500-row corpus available", () => {
    expect(corpus.length).toBe(500);
  });

  it("decodes every corpus capsule from base32 identically to Python", () => {
    for (const row of corpus) {
      expectMatchesCorpusCapsule(decodeCapsule(row.base32), row.capsule);
    }
  });

  it("decodes every corpus capsule from hex identically to Python", () => {
    for (const row of corpus) {
      expectMatchesCorpusCapsule(decodeHex(row.hex), row.capsule);
    }
  });

  it("rejects a payload of the wrong byte length", () => {
    expect(() => decodeHex("00")).toThrow();
  });

  it("is pure: no network, filesystem, or clock reference in the source", () => {
    const src = readFileSync("src/shared/capsule/decode.ts", "utf8");
    for (const banned of ["fetch(", "Date.now", "new Date", "require(", "localStorage", "XMLHttpRequest"]) {
      expect(src).not.toContain(banned);
    }
  });
});
