# Reason codebook — design

Phase 4, DHRUVA. Written 2026-09-13.

The capsule spends 8 bits on `reason_code` (offset 125). Those 8 bits are the
entire explanation a crew hears when the phone has no network: the server picks
an index, the phone expands it into a spoken sentence from a codebook that
shipped with the app. This document specifies how the index is constructed, what
the codebook contains, and how the phone behaves when the byte arrives damaged.

Scope: the codebook, its generator, its lexicons, and `reason_index()`. Out of
scope: the TypeScript decoder port, QR transport, and wiring node 9 to the full
capsule encoder — all phase 4, all separate tasks.

---

## 1. Why the index is structured rather than enumerated

An enumerated codebook — 256 sentences in a list — puts the meaning of index 90
nowhere but the list. Every phone in the field holds a copy, so renumbering to
add a rule silently changes what an already-shipped handset says. The 500-capsule
corpus in `eval/capsule_corpus.jsonl` would also need rewriting, and that corpus
is the contract between the Python and TypeScript implementations.

A structured index makes the byte self-describing. `reason_index()` computes it
from the assessment; the decoder takes it apart with shifts. Neither side holds a
lookup table the other lacks, which is the same discipline `fields.py` already
applies to the capsule itself: one table, both directions generated from it.

The cost is density. Not all 256 combinations are reachable — 69 are, per
`generate_codebook.reachable_keys()` — and the rest are structurally impossible
(a tsunami that is not a no-go). They
still get entries, because Gate 4 requires exactly 256 renderable entries. See
§5.

## 2. Bit layout

```
reason_code : 8 bits, MSB-first

  bits 7-6   band       2 bits   mirrors risk_class
  bits 5-3   family     3 bits   deciding-rule family
  bits 2-0   modifier   3 bits   secondary clause
```

**Band values mirror `risk_class` (offset 57) exactly:**

| Band | Meaning | `RiskClass` |
|---:|---|---|
| 0 | safe | `SAFE` |
| 1 | caution | `CAUTION` |
| 2 | no-go | `NO_GO` |
| 3 | unknown | `UNKNOWN` |

The mirror is the point. The capsule now carries the verdict twice, 68 bits
apart, and coherence is a single comparison:

```
reason_code >> 6 == risk_class
```

Note that this encoding is **not monotonic in severity** — no-go is `10`, and
flipping the high bit yields `00`, safe. Banding therefore buys nothing on its
own; the protection is entirely the cross-check between the two copies. §6
specifies what happens when they disagree.

**Family values (bits 5-3):**

| Family | Meaning | Source `rule_id` |
|---:|---|---|
| 0 | generic / unspecified | — (degradation target) |
| 1 | wave | `WAVE-S1`, `WAVE-C2`, `WAVE-N3` |
| 2 | wind | `WIND-S1`, `WIND-C2`, `WIND-N3` |
| 3 | cyclone | `CYCLONE-A1` |
| 4 | lightning | `LIGHTNING-A2` |
| 5 | tsunami | `TSUNAMI-A3` |
| 6 | data missing | `DATA-U0` |
| 7 | reserved | — |

The family comes from the prefix of `RiskAssessment.deciding_rule.rule_id`; the
band comes from `RiskAssessment.risk_class`. The rule-id suffix (`S1`/`C2`/`N3`/
`A*`/`U0`) already encodes the verdict, so the two are independently derived and
their agreement is itself a consistency check worth asserting in tests.

Families 3, 4 and 5 are the absolute overrides. `assess()` returns early when one
fires, so they can never co-occur with a wave or wind family.

**Modifier values (bits 2-0)** — every one computable from a capsule field or the
assessment. Nothing here is invented:

| Mod | Meaning | Computed from |
|---:|---|---|
| 0 | none | — |
| 1 | value saturated | `saturating_fields()` — renders "at least X" |
| 2 | boundary near | `bnd_dist_nm`, `bnd_type`, `bnd_eta_min` |
| 3 | PFZ reachable | `pfz_dist_nm`, `pfz_bearing`, `pfz_conf` |
| 4 | PFZ outranked by hazard | PFZ present **and** band ≥ 1 |
| 5 | return now | reserved route bits, `risk_class == 2` only |
| 6 | thresholds provisional | `PROVISIONAL` in `risk/thresholds.py` |
| 7 | reserved | — |

Modifier 1 exists because a saturating capsule field is a lie if rendered as
exact. `wave_hs` rails at 7.75 m; a 9 m sea encodes as 7.75 and must be spoken as
"at least 7.75 metres", never "7.75 metres".

Note the namespace trap: `saturating_fields()` returns **wire** names
(`wave_hs`, `sst`) while templates read **decoded** attributes (`wave_hs_m`,
`sst_c`). The generator holds the bridge table in §7 and asserts it covers every
saturable field, so a rename on either side fails a test rather than silently
disabling modifier 1.

Modifier 4 encodes the rule from `CLAUDE.md`: a favourable fishing zone never
renders above an active hazard. When a PFZ is present and the band is caution or
worse, the sentence names the hazard first and the zone second, or not at all.

Modifier 6 carries the honesty flag. While `PROVISIONAL = True`, sentences that
cite a threshold must say the threshold is provisional and not INCOIS Ocean State
Forecast criteria.

## 3. Reachability

| Band | Families reachable | Notes |
|---|---|---|
| 0 safe | 0, 1, 2 | overrides are always no-go; data-missing is always unknown |
| 1 caution | 0, 1, 2 | same |
| 2 no-go | 0, 1, 2, 3, 4, 5 | the only band where overrides appear |
| 3 unknown | 0, 6 | `DATA-U0` only |

Modifier constraints:

- `1 saturated` — families 1 and 2 only (the only families naming a rail-able field)
- `3 PFZ reachable` — bands 0 and 1 only
- `4 PFZ outranked` — bands 1 and 2 only
- `5 return now` — band 2 only
- `2 boundary near`, `6 provisional` — any band
- `7` — never

Reachability is declared in `structure.yaml`, not hard-coded in the generator, so
the constraint table and the tests read from one source.

## 4. Storage

```
data/codebook/
  structure.yaml            bands, families, modifiers, reachability, slot grammar
  lexicons/<lang>.yaml      compass points, enum labels, units  (12 files)
  templates/<lang>.yaml     authored prose, reachable combinations only  (12 files)
  build/<lang>.json         generated: 256 entries each  (12 files, checked in)
```

`structure.yaml` is the single source of truth, in the same sense `fields.py` is
for the capsule. The generator reads it plus the per-language templates and
lexicons and emits `build/<lang>.json`.

The build output is **checked in** because the decoder is pure — no filesystem at
runtime — so the PWA imports the JSON as a module and the Python side loads it at
import time. Checked-in generated files can drift from their source, so CI
regenerates and diffs; a mismatch fails the build.

### Lexicons are a separate deliverable from templates

Templates need more than sentences. `{wind_dir}` must render as a compass point
name in the target language, not a number — "north-east", "வடகிழக்கு". So each
language needs:

- 16 compass point names
- `bnd_type` labels: none / IMBL / marine protected area / closed area
- `chl_class` labels: low / moderate / high / very high
- `msg_type` labels: advisory / alert / all-clear / test
- unit names: metres, knots, nautical miles, minutes, degrees Celsius —
  needed as a lexicon rather than only as authored prose, because the generated
  generic and unreachable entries (§5) compose their sentences programmatically

These are not numbers, so the firewall does not police them, but a wrong compass
point sends a boat the wrong way. They are authored and reviewed like the
sentences.

## 5. All 256 entries exist

`IMPLEMENTATION.md:138` requires exactly 256 entries, every one rendering in all
12 languages. The ~215 unreachable combinations are generated, not authored: each
carries `reachable: false` and renders its **band's generic text** (family 0,
modifier 0). A phone that somehow decodes band 0 with family 5 therefore speaks
the safe-band generic sentence and raises `degraded`, rather than speaking
nothing or speaking about a tsunami in a safe advisory.

## 6. Degradation

```
decode_reason(reason_code: int, risk_class: int) -> ReasonRender
    band, family, modifier, degraded: bool, text: str
```

Three cases:

1. **Coherent and reachable** — render the authored entry.
2. **Band disagrees with `risk_class`** — take the more severe of the two under
   the `_SEVERITY` order already in `risk/rules.py` (`SAFE` 0 < `UNKNOWN` 1 <
   `CAUTION` 2 < `NO_GO` 3), then render that band's generic entry. Family and
   modifier bits are **discarded**: if the band bits are corrupt the rest may be
   too. `degraded = True`.
3. **Coherent but unreachable** — render the band's generic entry,
   `degraded = True`.

The UI shows `degraded` as "part of this advisory could not be read — seek the
official INCOIS or IMD bulletin". Never silently.

Taking the worse band rather than trusting either copy follows the rule the risk
engine already states: a system that answers "safe" when it does not know is
worse than one that answers nothing.

## 7. The codebook satisfies the numeric firewall by construction

Slots bind to attributes of the decoded `Capsule` (`codec.py`), **not** to the
wire field names in `fields.py`. The two namespaces differ and the difference is
a live bug source:

| wire (`fields.py`) | decoded (`Capsule`) |
|---|---|
| `wave_hs` | `wave_hs_m` |
| `sst` | `sst_c` |
| `wind_dir` | `wind_dir_deg` |
| `curr_dir` | `curr_dir_deg` |
| `pfz_bearing` | `pfz_bearing_deg` |
| `zone_id` + `lat_offset` / `lon_offset` | `lat` / `lon` |

Three slot kinds, all declared in `structure.yaml`:

- **direct** — a `Capsule` attribute rendered as a number:
  `{wave_hs_m}`, `{wind_kt}`, `{curr_kt}`, `{sst_c}`, `{pfz_dist_nm}`,
  `{bnd_dist_nm}`, `{bnd_eta_min}`, `{valid_hours}`
- **converted** — the unit conversions `CLAUDE.md` already permits, and only
  those: `{wave_hs_ft}` (m→ft), `{wind_kmh}` (kt→km/h)
- **lexicon** — a `Capsule` attribute mapped through the per-language lexicon to
  a word, rendering **no digits**: `{wind_dir_name}`, `{curr_dir_name}`,
  `{pfz_bearing_name}`, `{bnd_type_name}`, `{chl_class_name}`, `{msg_type_name}`

Lexicon slots are named `_name` precisely so that `{wind_dir_deg}` (the number
337.5) and `{wind_dir_name}` ("north-northwest") can never be confused in a
template. A bearing spoken as a number is useless to a crew; a bearing spoken as
the wrong compass point is dangerous.

Capsule attributes are themselves quantised from evidence. A rendered codebook
sentence therefore cannot contain a number that is not evidence-backed. This is
not an exemption from the numeric firewall — it is a structural proof of
compliance, and it is enforced statically (§8, tests 4 and 8) rather than trusted.

## 8. Tests, written first

1. `reason_code >> 6 == risk_class` for all 256 indices.
2. For every rule in the catalogue, `reason_index()` returns an index whose band
   matches the assessment's `risk_class`, and whose family matches the
   `deciding_rule` prefix.
3. All 12 built files have exactly 256 entries with identical key sets.
4. Every slot name in every template resolves to a `Capsule` attribute, a
   declared conversion, or a lexicon key — checked against `codec.py`, not
   `fields.py` (§7).
5. Mismatch → worse band, generic entry, `degraded = True`.
6. Unreachable index → band generic entry, `degraded = True`.
7. All 500 corpus capsules render a non-empty sentence in all 12 languages with
   no unfilled slots.
8. **No template contains a literal number outside a slot.** ASCII and Indic
   digits are checked in all 12 languages immediately. Spelled-out numerals are
   checked via the firewall's own `_WORD_NUMBERS` tables, which today exist for
   `en`, `ta` and `hi` only — the check extends to each language as its table
   lands (§10).
9. The wire↔decoded bridge table covers every name `saturating_fields()` can
   return; an unmapped name fails rather than silently disabling modifier 1.
10. Generator is deterministic: regenerating `build/` produces no diff.

## 9. Wiring

`reason_index(assessment: RiskAssessment) -> int` lands in
`backend/dhruva/codec/reason.py` and replaces the stub at
`backend/dhruva/graph/build.py:395`, which currently hardcodes
`{SAFE: 1, CAUTION: 41, NO_GO: 90}` — three magic indices that predate the
codebook and map no rule at all.

Node 9's remaining job, calling the capsule encoder that already exists, stays
out of scope here and is tracked as its own task.

## 10. Known gaps this design creates

**Nine languages have no spelled-out numeral table.** `firewall.py` covers `en`,
`ta`, `hi`. Until the other nine land, test 8 checks digits but not spelled-out
numerals for those languages. Writing the tables is part of this work.

**Machine-authored safety text in twelve languages has not been read by native
speakers.** The templates will be drafted here; a crew acting on a mistranslated
no-go is the failure mode this whole project exists to prevent. No public demo or
field use before native review of at least the no-go band. Recorded here rather
than discovered later, in the same spirit as the provisional thresholds.

**The twelfth language is a guess.** Tamil, Telugu, Malayalam, Kannada, Marathi,
Konkani, Gujarati, Odia, Bengali, Hindi, English cover every coastal state and
UT; Urdu is the twelfth and is not derived from a requirement.

**Codebook structure is versioned by `schema_ver`.** The capsule's 3-bit
`schema_ver` (offset 4) covers the field table today. Any change to bands,
families or modifiers changes what a shipped phone hears and must bump it. With
3 bits there are 8 versions total before wrap — a budget worth stating now rather
than discovering at version 8.
