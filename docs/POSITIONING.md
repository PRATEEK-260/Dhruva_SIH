# Positioning — DRAFT, not yet adopted

Drafted 2026-09-28, revised the same day after research. Nothing in `CLAUDE.md`,
`dhruva-plan.html` or `dhruva-pitch.html` has been changed to match this. It proposes a change
to the settled thesis, so it needs a decision before any of it lands.

---

## Three findings that drive everything below

**1. The problem statement never asks for offline delivery.** PS 26176 is *"ORCA — Marine
EcOsystem Reasoning with Collaborative Agents"* ([full text][ps]). It asks for an agentic,
multi-agent **conversational platform**: interpret intent, decompose requests, coordinate
specialised agents, reason across datasets, answer in the user's own Indian language, hold a
multi-turn conversation, and back every recommendation with evidence, maps and charts. The words
NavIC, satellite messaging and offline do not appear. The capsule is our addition, not the ask.

**2. Getting alerts to boats is solved, several times over, and ISRO built most of it.**
DAT-SG, GEMINI, the NavIC Messaging Receiver, VCSS + Nabhmitra, INCOIS SAMUDRA and MSSRF's
Fisher Friend all deliver PFZ, forecasts and warnings, most in regional languages, some with
audio alerts. What none of them do — in anything found — is **take a question and answer it**.

**3. The capsule has a real, documented home.** ISRO's public ICD for DAT-SG
([v1.2][dat-icd]) defines a control-room message (NavIC message ID 41) **addressed to one boat
by a 24-bit terminal ID**, with a text payload of **23 bytes (184 bits)**. The capsule is 145
bits: 19 raw bytes, or exactly 23 printable characters in base-85. One DAT-SG message, one boat,
one answer. That is a far stronger claim than "fits a NavIC segment".

---

## The new one-liner

> **DHRUVA is the ORCA the problem statement asks for: a fisherman asks a question in his own
> language and gets an answer for his boat, his spot, this morning, with every number traced to
> the satellite data it came from. And when he is out of network, the same answer fits in a
> single message on the DAT-SG link ISRO already runs.**

Lead with the conversation and the evidence. The capsule becomes the answer to the judge's
obvious follow-up — "what about 20 km out?" — instead of the headline.

---

## What already exists

| System | Operator | What it does | Q&A? |
|---|---|---|---|
| DAT (2010) | ISRO | One-way distress alert over INSAT | No |
| DAT-SG | ISRO | Distress + acknowledgement; receives INCOIS PFZ and warnings over NavIC; per-boat text messages (23 bytes) and six predefined emergency codes; Bluetooth to a phone app. "Limited short messaging" boat→hub | No |
| NavIC Messaging Receiver | ISRO | NavIC broadcast receiver, Bluetooth, audio alarm; app with **audio/visual alerts in 13 regional languages**; boundary-crossing alert | No |
| GEMINI (2019) | INCOIS + AAI | PFZ, ocean state forecast, disaster warnings over GAGAN; app in 9 languages | No |
| VCSS + Nabhmitra | Dept of Fisheries, ₹364 cr, PMMSY; app by SAC-ISRO | Transponders on one lakh boats via GSAT. Position reporting, two-way messaging, predefined SOS ("Fire on Boat", "Boat Sinking"), weather and cyclone warnings in 7 languages, PFZ, offline maps, geofence alerts, e-token | No |
| SAMUDRA | INCOIS | Official app: PFZ, five-day ocean state forecast, **tides**, marine heatwaves, currents, tsunami alerts; maps and charts; 8 languages | No |
| Fisher Friend (FFMA) | MSSRF + Qualcomm + INCOIS | PFZ, OSF, alerts, market prices, GPS to PFZ; audio help in 3 languages | No |
| Blue Voice (Mar 2026) | Pondicherry University | Location-specific weather; fishers contribute their own knowledge | Unclear — check |

Also relevant: the MSS terminal behind VCSS runs a **9.6 kbps forward / 2.4 kbps return** link
([ISRO, ICG-14][icg14]). Bandwidth is not scarce on VCSS, so the capsule's compression only
matters on NavIC and DAT-SG. NavIC messaging gives each broadcaster its own message ID through
ISRO's WIMS portal, "definition of 220 bits is left to user", and ISRO is integrating the
Common Alerting Protocol (CAP) into the broadcast ([ICG-16][icg16]).

---

## Claims to cut or rewrite

| Where | Current claim | Why it must go | Replace with |
|---|---|---|---|
| `dhruva-pitch.html:269`, `PROJECT_CONTEXT.md:144` | "His signal dies. This is where every other app of this kind goes blank." | DAT-SG, NMR, GEMINI and Nabhmitra all work there | "His signal dies. The alert systems on his boat still get bulletins — but none can answer him. DHRUVA's answer fits in one DAT-SG message addressed to his boat." |
| `PROJECT_CONTEXT.md:158` | Our wedge is working offshore | Offshore delivery is ISRO's; the PS asks for reasoning | The wedge is a *personal, explained answer to a question*; offshore is a bonus on existing links |
| `dhruva-pitch.html:232`, `PROJECT_CONTEXT.md:164` | Thesis leads with "145 bits, one NavIC segment" | Leads with the part the PS doesn't ask for | Lead with the conversation; cite the DAT-SG 23-byte fit as supporting evidence |
| `PROJECT_CONTEXT.md:88` | Every NavIC receiver gets it "with no new infrastructure" | Needs ISRO to allot a message ID or INCOIS to use message 41 | "Fits an existing DAT-SG message; adoption is a message definition, not hardware" |
| Voice-first as a differentiator | "Regional-language audio" | NMR app already does audio alerts in 13 languages | *Conversational* voice: he asks, it answers |
| Plan scene "09:20 DRIFTING" | Boundary alert as a headline | NMR and Nabhmitra already alert on boundary crossing | Only *predictive* ETA from drift is new, and `route` is still a stub |

Keep: the numeric firewall, evidence cards, the 145-bit field table, QR/Bluetooth/SMS as demo
stand-ins for the DAT-SG link.

---

## What the PS asks for that DHRUVA does not do yet

Checked against the code, not the plan.

| PS requirement | State in the repo |
|---|---|
| Autonomous planning, tool selection, collaborating agents | Keyword `classify()` placeholder; no LLM wired (`graph/build.py:225`) |
| Detect the query's language, reply in it | Not built — language is passed in |
| Multi-turn conversation | Not built — no checkpointer or thread ID wired |
| Tides near my location | **No tide source at all.** `Variable` has no tide; SAMUDRA shows tides, judges will ask |
| Lightning and cyclone alerts in my area | Lightning rule exists (`risk/rules.py:115`) but **nothing feeds it**; cyclone feed not checked |
| Safest route | `route` is a stub (`graph/build.py:381`) |
| Geofence notifications when *approaching* boundaries | Boundaries in PostGIS; no proactive notification |
| Proactive alerts | Request/response only |
| Charts | Study routes (time series, anomaly explorer) outstanding |
| "Why has productivity declined?" | Heatwave baseline registered in phase 3; end-to-end answer not verified |
| Evidence-backed recommendations | **Done** — the firewall and evidence bundle are the strongest thing we have |
| High chlorophyll + favourable SST regions | Data and raster layers exist; no query path verified |

**Build priority implied:** LLM planner → language detection + multi-turn → a tide source →
voice. Those are PS requirements the judges will test directly. Offline storage and the
capsule polish come after.

---

## Making the existing systems better

### 1. One answer, one boat, one DAT-SG message — *strongest, and documented*

The DAT-SG control room can already send a 23-byte message to a single terminal. The capsule is
19 bytes. So: fisherman asks (VCSS messaging via Nabhmitra, or before leaving port; DAT-SG
has no return message for a question, see `docs/DATSG_ICD.md`) → shore graph answers → one addressed DAT-SG message → phone rebuilds the full
spoken answer, in his language, from the codebook.

*Have:* graph, codec, codebook renderer, QR/BT demo transport.
*Done (29 Sep):* `frontend/src/shared/channel/datsg.ts` frames the capsule as ICD Table 8
message 41: control word 0x3 (text), 23 base-85 characters, tested over the 500-capsule corpus.
*Verify:* whether the 0x3 text payload is 8-bit clean or printable-only (base-85 needs printable
ASCII; raw needs 8-bit clean).

### 2. Emit alerts as CAP

ISRO is wiring the Common Alerting Protocol into NavIC broadcast, and CAP is the standard format
for disaster alerts. DHRUVA's NO-GO verdicts as CAP messages plug straight into that pipeline
instead of asking anyone to adopt a new format. Cheap to build: CAP is a documented XML schema.

### 3. Personal answers from a broadcast

NavIC broadcasters get their own message ID. Broadcast a compact per-cell risk grid; each phone
reads its own cell. GEMINI and NMR users get "your spot" instead of "your coast".
*Missing:* grid format and bit budget, not sized.

### 4. Hazard-aware PFZ

Filter or annotate a PFZ advisory that sits under an active hazard. NO-GO outranks PFZ.
*Blocker:* thresholds are placeholders until replaced with INCOIS criteria.

### 5. Predictive boundary warning

"At this heading you reach the line in N minutes" — before the geofence fires.
*Missing:* drift projection; `route` is a stub.

### 6. Catch reports score the PFZ

Nothing in any system found measures whether a PFZ advisory was right. Not built; phase 6.

Dropped from the earlier draft: "speak INCOIS messages aloud" — the NMR app already does audio
alerts in 13 languages.

---

## Still open

1. **Nabhmitra hands-on.** Everything above is from news, ISRO decks and store listings. Install
   it (Play Store: "Xponder", Saankhya Labs / Accord Software builds) and confirm it has no Q&A.
2. **Blue Voice.** Pondicherry University, March 2026. The article does not say whether it is
   conversational. If it is, it is the closest competitor.
3. **DAT-SG payload encoding** — see idea 1.
4. **Is VCSS the MSS network from the 2019 ICG deck?** Very likely, not confirmed.

---

## Sources

- [SIH26176 problem statement text][ps] (community mirror of the SIH 2026 list)
- [ISRO — ICD for DAT-SG v1.2][dat-icd]
- [ISRO — Signal-in-space ICD for INCOIS messages via NavIC][incois-icd]
- [ISRO, ICG-14 (2019) — NavIC and MSS based messaging][icg14]
- [ISRO, ICG-16 (2022) — NavIC messaging service update][icg16]
- [ISRO — DAT-SG](https://www.isro.gov.in/Second_Generation_DistressAlertTransmitter.html)
- [PIB — GEMINI launch](https://pib.gov.in/newsite/PrintRelease.aspx?relid=193703)
- [GS Times — VCSS national rollout](https://www.gstimes.in/national-rollout-of-the-vessel-communication-and-support-system-vcss/)
- [Vikaspedia — Nabhmitra app](https://en.vikaspedia.in/viewcontent/agriculture/fisheries/advisories-for-fisheries-sector/nabhmitra-app-for-indian-fishermen?lgn=en)
- [Civilsdaily — Nabhmitra](https://www.civilsdaily.com/news/nabhmitra-satellite-based-safety-device-for-fishermen/)
- [INCOIS — SAMUDRA](https://incois.gov.in/site/SAMUDRA/index.html)
- [MSSRF — Fisher Friend audio option](https://www.mssrf.org/small-news/audio-option-boat-destination-tracking-check-out-new-features-of-fisher-friend-mobile-application/)
- [News on AIR — Blue Voice](https://www.newsonair.gov.in/pondicherry-university-launches-blue-voice-app-for-coastal-fishers)

[ps]: https://github.com/NoBugNinja/Smart-India-Hackathon-SIH-2026-Problem-Statements/blob/main/README_DETAILED.md
[dat-icd]: https://www.isro.gov.in/media_isro/pdf/Missions/icd_for_dat-sg_22feb2021_v1.2.pdf
[incois-icd]: https://www.isro.gov.in/media_isro/pdf/SateliteNavigation/1a_messgingicd_receiver_incois_approved_ver_1.2.pdf
[icg14]: https://www.unoosa.org/documents/pdf/icg/2019/icg14/15.pdf
[icg16]: https://www.unoosa.org/documents/pdf/icg/2022/ICG16/wgc-04.pdf
