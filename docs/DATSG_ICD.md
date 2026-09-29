# What ISRO's DAT-SG ICD allows, and what it does not

Source: ISRO, *Interface Control Document of Distress Alert Transmitter – Second Generation
(DAT-SG): Emergency Messaging with Acknowledgement via NavIC Messaging Service*, version 1.2,
February 2021, `ISRO-IRNSS-ICD-DAT-1.2`.
<https://www.isro.gov.in/media_isro/pdf/Missions/icd_for_dat-sg_22feb2021_v1.2.pdf>
Read on 29 Sep 2026. Section and table numbers below are the ICD's.

## Shore to boat: yes, and the capsule fits

- NavIC broadcasts a 292-bit sub-frame (§6.2.1.7, Figure 4). Of that, **220 bits are DAT-SG
  message data**, under a 6-bit message ID. Message ID 41 is the DAT-SG control room; 20 is
  INCOIS PFZ and 21 is INCOIS warnings (§6.2, §6.2.1.8).
- The 220 bits of a message-41 frame are laid out in Table 8:

  | Bits | Field | Size |
  |---|---|---|
  | 0–23 | Terminal ID, the one boat it is addressed to | 24 |
  | 24–26 | Control word: 0x1 emergency code, 0x2 manual ack, 0x3 text, 0x4 auto ack | 3 |
  | 27–31 | Message length, in bytes of valid payload | 5 |
  | 32–215 | Data payload | 184 (23 bytes) |
  | 216–219 | Reserved | 4 |

- A **text message (control word 0x3) carries at most 23 bytes** to one terminal (§8.1.3). The
  ICD does not say which character set the text uses.
- The capsule is 145 bits, which is **19 bytes**. Sent as text (below) it becomes 23 characters.

What the ICD does not give us: a control word for binary data (0x5–0x7 are unassigned). So
DHRUVA sends the capsule as an ordinary **text message, control word 0x3**: the 145 bits written
as 23 base-85 characters (85^23 ≈ 2^147.4), which fill the payload exactly. The alphabet is
RFC 1924's printable ASCII; the ICD does not name a character set, so that is an assumption to
confirm with ISRO. `frontend/src/shared/channel/datsg.ts` builds the 220-bit frame and parses it
back, tested over the 500-capsule corpus. It is ISRO's control room that would send it; no team
transmits.

## Boat to shore: no general message

- DAT-SG transmits on the INSAT/GSAT UHF (DRT) transponder (Preface), and the only boat-to-shore
  packet in the ICD is the **distress alert** (§9, Table 14): 112 bits, carrying terminal ID,
  nodal MRCC, position, time and **one 8-bit emergency field**.
- That field has fixed values only: Fire, Medical, Boat sink, Man overboard, Test, All OK,
  Terrorist attack. There is no free-text or short-message uplink, and no spare code a question
  could use without ISRO changing the terminal.

**Consequence for DHRUVA.** A fisherman's question cannot go up over DAT-SG. It goes up over
Nabhmitra's two-way messaging on VCSS, the channel DHRUVA is built for, which is simulated in
this prototype because its message format is not public. Only the answer comes down in a DAT-SG
message 41.

## Also in the ICD, worth knowing

INCOIS already broadcasts PFZ (message 20) and high-wave, cyclone and tsunami warnings
(message 21) over NavIC to DAT-SG. Their format is in a separate ICD, *Signal-In-Space ICD for
INCOIS Messages via NavIC Messaging Service v1.1*. DHRUVA does not claim to be the first thing
that reaches a boat offshore. What it adds is an answer to that boat's own question, with the
reasons behind it.
