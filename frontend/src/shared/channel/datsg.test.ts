import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";
import { decodeBase32, decodeCapsule, decode } from "../capsule/decode";
import {
  CONTROL_TEXT,
  LAYOUT,
  MESSAGE_BITS,
  PAYLOAD_BYTES,
  TEXT_CHARS,
  capsuleToText,
  demoTerminalId,
  frame,
  parse,
  textToCapsule,
} from "./datsg";

// The 500-capsule cross-language corpus the decoder is tested against.
const samples: string[] = readFileSync("../eval/capsule_corpus.jsonl", "utf8")
  .trim()
  .split("\n")
  .map((line) => (JSON.parse(line) as { base32: string }).base32);

describe("DAT-SG message 41 (ICD v1.2 Table 8)", () => {
  it("lays out 220 bits with no gap or overlap", () => {
    let at = 0;
    for (const f of LAYOUT) {
      expect(f.from).toBe(at);
      at += f.width;
    }
    expect(at).toBe(MESSAGE_BITS);
  });

  it("carries every corpus capsule as a 23-character text message and back", () => {
    expect(samples.length).toBeGreaterThan(0);
    for (const b32 of samples) {
      const bytes = decodeBase32(b32);
      const text = capsuleToText(bytes);
      expect(text).toHaveLength(TEXT_CHARS);
      expect(text).toMatch(/^[\x21-\x7e]+$/);
      const msg = parse(frame(demoTerminalId(), text));
      expect(msg.controlWord).toBe(CONTROL_TEXT);
      expect(msg.length).toBe(PAYLOAD_BYTES);
      expect(msg.terminalId).toBe(demoTerminalId());
      expect(decode(textToCapsule(msg.text))).toEqual(decodeCapsule(b32));
    }
  });

  it("uses the whole 23-byte payload and nothing more", () => {
    expect(TEXT_CHARS).toBe(PAYLOAD_BYTES);
    expect(() => frame(1, "x".repeat(PAYLOAD_BYTES + 1))).toThrow();
  });

  it("refuses text that would overflow 145 bits", () => {
    expect(() => textToCapsule("~".repeat(TEXT_CHARS))).toThrow(/145 bits/);
  });

  it("shapes the demo terminal ID like Table 14's TID", () => {
    const id = demoTerminalId();
    expect(id >> 23).toBe(1);
    expect((id >> 18) & 0x1f).toBe(0x1); // Chennai MRCC
  });
});
