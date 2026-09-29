// Nabhmitra, SAC-ISRO's app on the Department of Fisheries' VCSS transponders:
// two-way messaging over GSAT. This is the channel DHRUVA is built for.
//
// Placeholder. Nabhmitra's message format is not public, so nothing here claims to
// match it. Questions go as the prototype's own one-byte code (shown on the phone
// as a QR, since this demo has no Bluetooth), and answers are demonstrated on
// DAT-SG's published frame instead. Replace both when the format is available.

import type { Channel } from ".";
import { uplinkPayload } from "../questions";

export const nabhmitra: Channel = {
  id: "nabhmitra",
  name: "Nabhmitra (VCSS)",
  short: "Nabhmitra",
  published: false,
  sendsQuestions: true,
  sendsAnswers: true,
  question: (code, lang) => uplinkPayload(code, lang),
  // No answer(): the format is not public, so ANSWER_CHANNEL is DAT-SG for now.
};
