// ISRO DAT-SG, ICD v1.2 (docs/DATSG_ICD.md). Shore to boat only: a control-room
// message, NavIC message ID 41, of 220 bits laid out as Table 8 and addressed to
// one terminal. DAT-SG has no boat-to-shore message a question could ride, so this
// adapter only sends.

import { CAPSULE_BYTES, TOTAL_BITS } from "../capsule/fields";

export const MESSAGE_ID = 41;
export const MESSAGE_BITS = 220;
export const PAYLOAD_BYTES = 23;
/** Table 8 control words. 0x5 to 0x7 are unassigned. */
export const CONTROL_TEXT = 0x3;

// RFC 1924's base-85 alphabet: printable ASCII without quotes, comma, full stop,
// slashes or space. The ICD does not name the text message's character set, so
// this is the most conservative 85 we could choose.
const ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz!#$%&()*+-;<=>?@^_`{|}~";
const BASE = 85n;
// 85^23 is about 2^147.4, so 23 characters hold the 145 bits and 22 would not.
export const TEXT_CHARS = 23;
const PAD_BITS = BigInt(CAPSULE_BYTES * 8 - TOTAL_BITS);

/** The 19-byte capsule as exactly 23 printable characters. */
export function capsuleToText(capsule: Uint8Array): string {
  if (capsule.length !== CAPSULE_BYTES) throw new Error(`capsule must be ${CAPSULE_BYTES} bytes, got ${capsule.length}`);
  let n = 0n;
  for (const b of capsule) n = (n << 8n) | BigInt(b);
  n >>= PAD_BITS;
  let out = "";
  for (let i = 0; i < TEXT_CHARS; i++) {
    out = ALPHABET[Number(n % BASE)] + out;
    n /= BASE;
  }
  return out;
}

export function textToCapsule(text: string): Uint8Array {
  if (text.length !== TEXT_CHARS) throw new Error(`capsule text must be ${TEXT_CHARS} characters, got ${text.length}`);
  let n = 0n;
  for (const ch of text) {
    const d = ALPHABET.indexOf(ch);
    if (d < 0) throw new Error(`not a capsule character: ${JSON.stringify(ch)}`);
    n = n * BASE + BigInt(d);
  }
  if (n >> BigInt(TOTAL_BITS) !== 0n) throw new Error(`capsule text holds more than ${TOTAL_BITS} bits`);
  n <<= PAD_BITS;
  const out = new Uint8Array(CAPSULE_BYTES);
  for (let i = CAPSULE_BYTES - 1; i >= 0; i--) {
    out[i] = Number(n & 0xffn);
    n >>= 8n;
  }
  return out;
}

export interface Message41 {
  terminalId: number;
  controlWord: number;
  /** Valid payload bytes. */
  length: number;
  text: string;
}

const bitsOf = (value: number, width: number) => value.toString(2).padStart(width, "0");

/** Table 8, as 220 bits most significant first: terminal ID 24, control word 3,
 * length 5, payload 184 (23 bytes, zero-filled past `length`), reserved 4. */
export function frame(terminalId: number, text: string): string {
  if (!Number.isInteger(terminalId) || terminalId < 0 || terminalId >= 2 ** 24) {
    throw new Error("terminal ID must fit 24 bits");
  }
  if (text.length > PAYLOAD_BYTES) throw new Error(`a text message holds at most ${PAYLOAD_BYTES} bytes`);
  const payload = [...text].map((ch) => {
    const c = ch.charCodeAt(0);
    if (c < 0x20 || c > 0x7e) throw new Error("text must be printable ASCII");
    return bitsOf(c, 8);
  });
  const bits =
    bitsOf(terminalId, 24) +
    bitsOf(CONTROL_TEXT, 3) +
    bitsOf(text.length, 5) +
    payload.join("").padEnd(PAYLOAD_BYTES * 8, "0") +
    "0000";
  if (bits.length !== MESSAGE_BITS) throw new Error(`frame is ${bits.length} bits`);
  return bits;
}

export function parse(bits: string): Message41 {
  if (bits.length !== MESSAGE_BITS || /[^01]/.test(bits)) throw new Error(`a message is ${MESSAGE_BITS} bits`);
  const num = (from: number, width: number) => parseInt(bits.slice(from, from + width), 2);
  const length = num(27, 5);
  if (length > PAYLOAD_BYTES) throw new Error(`length ${length} exceeds the payload`);
  let text = "";
  for (let i = 0; i < length; i++) text += String.fromCharCode(num(32 + i * 8, 8));
  return { terminalId: num(0, 24), controlWord: num(24, 3), length, text };
}

/** Where each Table 8 field starts and ends, for drawing the frame. */
export const LAYOUT = [
  { name: "Terminal ID", from: 0, width: 24 },
  { name: "Control word", from: 24, width: 3 },
  { name: "Length", from: 27, width: 5 },
  { name: "Payload", from: 32, width: 184 },
  { name: "Reserved", from: 216, width: 4 },
] as const;

/** A terminal ID shaped like Table 14's TID: a leading 1, the nodal MRCC (Chennai
 * is 0x1), then an 18-bit terminal number. The number here is made up for the demo. */
export function demoTerminalId(terminal = 0x2a51): number {
  return (1 << 23) | (0x1 << 18) | (terminal & 0x3ffff);
}
