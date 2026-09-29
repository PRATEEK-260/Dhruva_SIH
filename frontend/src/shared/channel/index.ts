// The links a question and its answer travel over, behind one interface so the
// rest of the app never names a channel.
//
// DHRUVA is built for Nabhmitra's two-way link on VCSS transponders. Nabhmitra's
// message format is not public, so the prototype is demonstrated against ISRO's
// published DAT-SG format (docs/DATSG_ICD.md). When Nabhmitra's format is
// available, its adapter replaces the placeholder and nothing else changes.

import type { Language } from "../capsule/codebook";
import { datsg } from "./datsg";
import { nabhmitra } from "./nabhmitra";

export interface AnswerFrame {
  /** What the channel carries, as bits most significant first. */
  bits: string;
  /** The payload inside the frame, as the channel's own text. */
  payload: string;
}

export interface Channel {
  id: "nabhmitra" | "datsg";
  name: string;
  /** The name as it reads mid-sentence. */
  short: string;
  /** Whether the wire format is published, so the prototype builds it byte for byte. */
  published: boolean;
  /** A boat can send a question over it. */
  sendsQuestions: boolean;
  /** A shore answer can come down it. */
  sendsAnswers: boolean;
  question?(code: number, lang: Language): string;
  answer?(capsule: Uint8Array, terminalId: number): AnswerFrame;
}

/** Up: DAT-SG has no boat-to-shore message a question could ride (ICD v1.2 Table 14). */
export const QUESTION_CHANNEL: Channel = nabhmitra;
/** Down: Nabhmitra is the target; DAT-SG is the published format the demo builds. */
export const ANSWER_CHANNEL: Channel = datsg;
export const TARGET_CHANNEL: Channel = nabhmitra;

export const CHANNELS: readonly Channel[] = [nabhmitra, datsg];
