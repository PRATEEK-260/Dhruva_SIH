# DHRUVA — context

Deep-sea Hazard, Routing & Understanding via Vernacular Agents. ISRO PS 26176 (ORCA).

This file is a fast orientation doc — what the project is, why it's built this way, and how
to answer the questions judges actually ask. For anything that changes as the build moves
(what's done, what's outstanding, test counts), read `docs/STATUS.md` instead of this file —
multiple sessions are actively building on this repo and STATUS.md is what's kept current.
`CLAUDE.md` is the full, authoritative project instructions file; this is a shorter derivative
of it plus material from conversation, not a replacement.

---

## The thesis, in one paragraph

Reasoning runs onshore, answers survive offshore. A full marine safety advisory — go/no-go
verdict, sea state, nearest fishing zone, boundary distance, why — compresses to **145 bits**,
small enough to fit inside a single 220-bit NavIC L5 message segment. A phone with zero
connectivity reconstructs a full spoken advisory, in a regional language, from those 145 bits
and a codebook shipped with the app at install time. No network, no cell tower, no signal
needed at the point of use.

## Why it's built this way — the two hard constraints

**No hardware, no transmission.** The NavIC uplink belongs to ISRO; no team gets to broadcast
on it. The project's claim is *segment conformance* — the 145-bit packet is provably, checkably
correct against ISRO's real 220-bit field format — not that this team has built or demonstrated
actual satellite transmission. Real delivery to open ocean would ride NavIC's own broadcast
once ISRO enables it; that's the piece nobody outside ISRO can build or demo.

**The LLM never emits a number.** Every figure that reaches a screen or a spoken sentence came
from a tool, not a model. An `EvidenceBundle` carries `{key, value, unit, dataset_id, cell,
valid_time}` for every number; narration is generated, then every numeric token in it — ASCII
digits, Indic digits, spelled-out numerals — is checked against the bundle. A number with no
evidence cannot render anywhere, including the shore console. This is the entire trust story.

## Other settled decisions (see CLAUDE.md for the full list)

- PFZ (fishing zone) data is **scraped**, not an API — always attributed with `source_url` and
  `fetched_at`, never presented as if a live feed exists.
- Boundary lines (EEZ/IMBL/MPA) are **indicative**, never legal — every rendered line carries
  that flag, and now (Shore Console) a visible dashed style and legend, not just a JSON property.
- Risk thresholds (`docs/THRESHOLDS.md`) are **engineering placeholders**, not yet validated
  against INCOIS's own Ocean State Forecast criteria — stated plainly, never presented as official.
- Absolute overrides beat everything: a cyclone warning within 300 km, lightning within 50 km,
  or any tsunami alert forces NO-GO regardless of what the computed wave/wind verdict says.
  A favourable fishing zone never renders above an active hazard.

## Stack, locked

LangGraph + Pydantic v2 orchestration · Gemini 2.5 Flash for planning (not yet wired — narration
is currently the firewall's own template) · Sarvam/Bhashini for voice (not yet wired) · FastAPI +
PostgreSQL/PostGIS backend · React + MapLibre frontend, two surfaces (Boat PWA, Shore Console) ·
QR / Bluetooth / SMS as the three transports the team controls for demoing the wire format,
distinct from NavIC itself.

---

## Judge Q&A — questions this project invites, and how to answer them

### "How does the 145-bit signal actually transmit and get received?"

It doesn't, by this team — and it isn't supposed to. The NavIC uplink is ISRO's alone; no team
gets spectrum access to it. What's actually proven is **segment conformance**: the 145-bit
capsule is built to fit exactly inside NavIC's real 220-bit L5 message format, checkable against
the field table on paper. The identical wire format also runs over QR, Bluetooth and SMS —
transports the team can actually build without hardware — which is what the demo uses to prove
the *decode* side works with zero connectivity. The moment ISRO puts this on their own broadcast,
every NavIC receiver in the Indian Ocean gets it, with no new infrastructure required.

### "So how does a QR code reach a fisherman in the middle of the ocean?"

It doesn't, by itself — a QR is a printed or displayed image; nothing about it transmits. It's
scanned at a landing centre or hub before the boat leaves shore (INCOIS already operates 586 of
these for PFZ bulletins), cached on the phone, then decoded fully offline once at sea — the exact
mechanism the demo shows. The genuine open-ocean, no-relay leg is NavIC's job, since satellite
broadcast already reaches anywhere with sky view. That's precisely the leg this team is honest
about not having built — the whole "segment conformance, not transmission" framing exists to
name that gap rather than paper over it.

### "Every output says 'advisory only, follow official INCOIS and IMD warnings' — why?"

Because DHRUVA computes a decision-support layer, not an authoritative warning. Concretely:
the risk thresholds are engineering placeholders, not yet validated against INCOIS's own
published criteria; PFZ data is scraped and could lag the real bulletin; boundary lines are
indicative, not surveyed legal lines. If DHRUVA were ever wrong and someone acted on it as if
it were official, that's a real safety failure. The notice is baked in redundantly at multiple
layers on purpose, so it's mechanically impossible to ship an advisory without it.

### "So are you just relaying their guidelines?"

No. INCOIS/IMD don't compute a personalized go/no-go for a specific boat class at a specific
lat/lon in real time — DHRUVA fuses wave height, wind, currents, SST, chlorophyll and boundary
proximity from half a dozen live sources and runs its own deterministic threshold engine to
produce that verdict. Then it delivers the result somewhere their own channels don't reach: a
phone with its radio fully off, speaking a regional language, from 145 bits. The disclaimer
reflects one specific fact about DHRUVA's own logic — an official cyclone/tsunami/lightning
warning is an absolute override above everything DHRUVA computes itself — not an admission that
the system does nothing on its own.
