# Phase 4 Completion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A phone with its radio off scans a QR capsule and speaks a full Tamil advisory, with the Python and TypeScript decoders proven identical against the 500-capsule corpus.

**Architecture:** The 8-bit `reason_code` is a structured index (2 band / 3 family / 3 modifier) computed from the risk assessment, never looked up. A generator turns one `structure.yaml` plus per-language templates and lexicons into 12 × 256 JSON files that both runtimes bundle. The TypeScript decoder is a port, not a reimplementation: `eval/capsule_corpus.jsonl` is the contract and CI runs both against it.

**Tech Stack:** Python 3.12 · pyyaml · segno (QR) · Vite · React 19 · TypeScript · vitest · jsQR

**Spec:** `docs/superpowers/specs/2026-09-13-reason-codebook-design.md`

## Global Constraints

- Python is pinned to **3.12** via uv. The system interpreter is 3.14 and lacks scientific wheels.
- Total capsule width is **exactly 145 bits**. No task may change it.
- The decoder is **pure**: no network, no filesystem, no clock, in either language.
- **Every quantiser clamps.** A value past the top of a scale saturates; wrapping is the worst bug this project can ship.
- **The LLM never emits a number.** Codebook templates may contain no literal digit outside a slot.
- Slots bind to decoded `Capsule` attributes (`wave_hs_m`, `sst_c`), **never** to wire field names (`wave_hs`, `sst`). The two namespaces differ.
- Commits are `area: imperative summary`. **No `Co-Authored-By` trailer** — the work ships under Prateek's name.
- Every advisory carries: *advisory only, follow official INCOIS and IMD warnings.*
- NO-GO outranks everything. A favourable fishing zone never renders above an active hazard.
- Run the `capsule-auditor` subagent after every codec change.
- Line length 100, `ruff check` and `ruff format --check` and `pyright` must stay clean.

---

## File Structure

**Create:**
- `data/codebook/structure.yaml` — bands, families, modifiers, reachability, slot grammar. Single source of truth.
- `data/codebook/lexicons/<lang>.yaml` × 12 — compass points, enum labels, unit words.
- `data/codebook/templates/<lang>.yaml` × 12 — authored prose for reachable combinations.
- `data/codebook/build/<lang>.json` × 12 — generated, checked in, 256 entries each.
- `backend/dhruva/codec/codebook.py` — `reason_index()`, `decode_reason()`, `render()`.
- `backend/dhruva/codec/generate_codebook.py` — the generator, run as a module.
- `backend/dhruva/codec/qr.py` — base32 ↔ capsule, QR image emit.
- `frontend/` — Vite + React 19 + TS project.
- `frontend/src/shared/capsule/fields.ts` — generated from `fields.py`.
- `frontend/src/shared/capsule/decode.ts` — the port.
- `frontend/src/shared/capsule/codebook.ts` — render from bundled JSON.
- `frontend/src/boat/ScanView.tsx` — camera scan, decode, speak.

**Modify:**
- `backend/dhruva/graph/build.py:395` — replace the hardcoded reason map.
- `backend/dhruva/evidence/firewall.py:76` — add nine numeral tables.
- `.github/workflows/ci.yml` — add the frontend job and the parity check.
- `backend/pyproject.toml` — add `segno` to the `data` extra.

---

### Task 1: Codebook structure and index arithmetic

**Files:**
- Create: `data/codebook/structure.yaml`
- Create: `backend/dhruva/codec/codebook.py`
- Test: `backend/tests/test_codebook_index.py`

**Interfaces:**
- Consumes: `RiskAssessment`, `RiskClass` from `dhruva.risk.rules`; `Capsule` from `dhruva.codec.codec`.
- Produces:
  - `reason_index(assessment: RiskAssessment, capsule: Capsule | None = None) -> int`
  - `split_reason(code: int) -> tuple[int, int, int]` returning `(band, family, modifier)`
  - `BANDS: dict[int, str]`, `FAMILIES: dict[int, str]`, `MODIFIERS: dict[int, str]`
  - `is_reachable(band: int, family: int, modifier: int) -> bool`

- [ ] **Step 1: Write `data/codebook/structure.yaml`**

```yaml
version: 1
bands:      {0: safe, 1: caution, 2: no-go, 3: unknown}
families:   {0: generic, 1: wave, 2: wind, 3: cyclone, 4: lightning, 5: tsunami, 6: data_missing, 7: reserved}
modifiers:  {0: none, 1: saturated, 2: boundary_near, 3: pfz_reachable, 4: pfz_outranked, 5: return_now, 6: provisional, 7: reserved}

rule_family:
  WAVE-S1: 1
  WAVE-C2: 1
  WAVE-N3: 1
  WIND-S1: 2
  WIND-C2: 2
  WIND-N3: 2
  CYCLONE-A1: 3
  LIGHTNING-A2: 4
  TSUNAMI-A3: 5
  DATA-U0: 6

reachable_families:
  0: [0, 1, 2]
  1: [0, 1, 2]
  2: [0, 1, 2, 3, 4, 5]
  3: [0, 6]

modifier_constraints:
  saturated:      {families: [1, 2]}
  pfz_reachable:  {bands: [0, 1]}
  pfz_outranked:  {bands: [1, 2]}
  return_now:     {bands: [2]}
  boundary_near:  {}
  provisional:    {}
  none:           {}
  reserved:       {bands: []}

# saturating_fields() returns wire names; templates read decoded attributes.
saturated_bridge:
  wave_hs: wave_hs_m
  wind_kt: wind_kt
  curr_kt: curr_kt
  sst: sst_c
  pfz_dist_nm: pfz_dist_nm
  bnd_dist_nm: bnd_dist_nm
  bnd_eta_min: bnd_eta_min
```

- [ ] **Step 2: Write the failing test**

```python
# backend/tests/test_codebook_index.py
import pytest
from dhruva.codec.codebook import reason_index, split_reason, is_reachable
from dhruva.graph.state import RiskClass
from dhruva.risk.rules import FiredRule, RiskAssessment


def _assessment(rule_id: str, verdict: RiskClass) -> RiskAssessment:
    return RiskAssessment(verdict, [FiredRule(rule_id, verdict, None, None, None, "", "")])


def test_band_always_equals_risk_class_for_every_index():
    for code in range(256):
        band, _family, _mod = split_reason(code)
        assert band == code >> 6


@pytest.mark.parametrize(
    "rule_id,verdict,family",
    [
        ("WAVE-S1", RiskClass.SAFE, 1),
        ("WAVE-N3", RiskClass.NO_GO, 1),
        ("WIND-C2", RiskClass.CAUTION, 2),
        ("CYCLONE-A1", RiskClass.NO_GO, 3),
        ("LIGHTNING-A2", RiskClass.NO_GO, 4),
        ("TSUNAMI-A3", RiskClass.NO_GO, 5),
        ("DATA-U0", RiskClass.UNKNOWN, 6),
    ],
)
def test_index_band_and_family_match_the_deciding_rule(rule_id, verdict, family):
    code = reason_index(_assessment(rule_id, verdict))
    band, fam, _mod = split_reason(code)
    assert band == {RiskClass.SAFE: 0, RiskClass.CAUTION: 1,
                    RiskClass.NO_GO: 2, RiskClass.UNKNOWN: 3}[verdict]
    assert fam == family


def test_overrides_are_unreachable_outside_the_no_go_band():
    assert not is_reachable(0, 5, 0)   # tsunami in the safe band
    assert not is_reachable(1, 3, 0)   # cyclone in the caution band
    assert is_reachable(2, 5, 0)


def test_data_missing_only_in_the_unknown_band():
    assert is_reachable(3, 6, 0)
    assert not is_reachable(0, 6, 0)


def test_saturated_bridge_covers_every_wire_name_saturating_fields_can_return():
    """Wire names (wave_hs, sst) differ from decoded attributes (wave_hs_m,
    sst_c). An unmapped name would silently disable the saturated modifier, so a
    9 m sea would be spoken as an exact 7.75 m."""
    from dhruva.codec.codec import Capsule, saturating_fields
    from dhruva.codec.codebook import SATURATED_BRIDGE

    railed = Capsule(wave_hs_m=99.0, wind_kt=999, curr_kt=99.0, sst_c=99.0,
                     pfz_dist_nm=999, bnd_dist_nm=999, bnd_eta_min=9999)
    for wire_name in saturating_fields(railed):
        assert wire_name in SATURATED_BRIDGE, f"{wire_name} missing from the bridge"
        assert hasattr(railed, SATURATED_BRIDGE[wire_name])
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_codebook_index.py -q`
Expected: `ModuleNotFoundError: No module named 'dhruva.codec.codebook'`

- [ ] **Step 4: Implement `codebook.py` index arithmetic**

Load `structure.yaml` once at import with `yaml.safe_load`. Implement:

```python
def split_reason(code: int) -> tuple[int, int, int]:
    if not 0 <= code <= 255:
        raise ValueError(f"reason_code out of range: {code}")
    return (code >> 6) & 0b11, (code >> 3) & 0b111, code & 0b111


def reason_index(assessment, capsule=None) -> int:
    band = _BAND_OF[assessment.risk_class]
    rule = assessment.deciding_rule
    family = RULE_FAMILY.get(rule.rule_id, 0) if rule else 0
    modifier = _modifier_for(assessment, capsule)
    if not is_reachable(band, family, modifier):
        family, modifier = 0, 0
    return (band << 6) | (family << 3) | modifier
```

`_modifier_for` picks the highest-priority applicable modifier in this order:
`return_now` (band 2 only), `saturated`, `pfz_outranked`, `boundary_near`,
`pfz_reachable`, `provisional`, `none`. Priority matters — only one modifier fits
in the byte, and a crew needs the most actionable clause.

- [ ] **Step 5: Run tests and confirm they pass**

Run: `.venv/bin/python -m pytest backend/tests/test_codebook_index.py -q`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add data/codebook/structure.yaml backend/dhruva/codec/codebook.py backend/tests/test_codebook_index.py
git commit -m "codec: add the structured reason index"
```

---

### Task 2: Degradation and the English codebook

**Files:**
- Create: `data/codebook/lexicons/en.yaml`, `data/codebook/templates/en.yaml`
- Create: `backend/dhruva/codec/generate_codebook.py`
- Modify: `backend/dhruva/codec/codebook.py`
- Test: `backend/tests/test_codebook_render.py`

**Interfaces:**
- Consumes: `split_reason`, `is_reachable` from Task 1.
- Produces:
  - `decode_reason(code: int, risk_class: int) -> ReasonRender` where
    `ReasonRender = dataclass(band: int, family: int, modifier: int, degraded: bool, text: str)`
  - `render(capsule: Capsule, language: str = "en") -> str`
  - `python -m dhruva.codec.generate_codebook` writing `data/codebook/build/<lang>.json`

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_codebook_render.py
from dhruva.codec.codebook import decode_reason


def test_coherent_code_renders_its_own_entry():
    code = (2 << 6) | (1 << 3) | 1          # no-go, wave, saturated
    out = decode_reason(code, risk_class=2)
    assert not out.degraded
    assert out.text


def test_mismatch_takes_the_worse_band_and_goes_generic():
    code = (0 << 6) | (1 << 3) | 0           # claims safe
    out = decode_reason(code, risk_class=2)  # capsule says no-go
    assert out.degraded
    assert out.band == 2                      # NO_GO outranks SAFE
    assert (out.family, out.modifier) == (0, 0)


def test_mismatch_between_safe_and_unknown_resolves_to_unknown():
    code = (0 << 6) | (1 << 3) | 0
    out = decode_reason(code, risk_class=3)
    assert out.degraded
    assert out.band == 3                      # UNKNOWN outranks SAFE in _SEVERITY


def test_unreachable_but_coherent_code_degrades_generic():
    code = (0 << 6) | (5 << 3) | 0            # tsunami in the safe band
    out = decode_reason(code, risk_class=0)
    assert out.degraded
    assert (out.family, out.modifier) == (0, 0)


def test_no_template_contains_a_literal_digit_outside_a_slot():
    import json, pathlib, re
    for path in pathlib.Path("data/codebook/build").glob("*.json"):
        for key, text in json.loads(path.read_text())["entries"].items():
            stripped = re.sub(r"\{[a-z_]+\}", "", text)
            assert not re.search(r"\d", stripped), f"{path.name}:{key} has a bare digit"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_codebook_render.py -q`
Expected: FAIL — `decode_reason` not defined.

- [ ] **Step 3: Write `lexicons/en.yaml`**

16 compass points (`N, NNE, NE, ENE, E, ESE, SE, SSE, S, SSW, SW, WSW, W, WNW, NW, NNW`
→ full English names), `bnd_type` labels (none / the maritime boundary / a marine
protected area / a closed area), `chl_class` (low / moderate / high / very high),
`msg_type` (advisory / alert / all-clear / test), unit words (metres, knots,
nautical miles, minutes, degrees Celsius).

- [ ] **Step 4: Write `templates/en.yaml` for reachable combinations**

Keyed `b<band>f<family>m<modifier>`. Example entries:

```yaml
b2f1m1: >-
  Do not go out. Waves are at least {wave_hs_m} metres, at or above the limit for
  your boat. Advisory only, follow official INCOIS and IMD warnings.
b2f3m0: >-
  Do not go out. A cyclone warning is in force near you. Return to the nearest
  harbour. Advisory only, follow official INCOIS and IMD warnings.
b1f2m2: >-
  Take care. Wind is {wind_kt} knots. You are {bnd_dist_nm} nautical miles from
  {bnd_type_name}, about {bnd_eta_min} minutes at your present drift. Advisory
  only, follow official INCOIS and IMD warnings.
b0f1m3: >-
  Conditions are within limits for your boat. Waves {wave_hs_m} metres, wind
  {wind_kt} knots. A fishing zone lies {pfz_dist_nm} nautical miles
  {pfz_bearing_name}. Advisory only, follow official INCOIS and IMD warnings.
b3f6m0: >-
  Conditions could not be confirmed, so no advice can be given. Seek the official
  INCOIS or IMD bulletin before going out.
```

Every band needs a `b<band>f0m0` generic entry — that is the degradation target.

- [ ] **Step 5: Write the generator**

Reads `structure.yaml` + `templates/<lang>.yaml` + `lexicons/<lang>.yaml`, emits
all 256 keys. Reachable keys take the authored text; unreachable keys take their
band's `b<band>f0m0` text and are marked `reachable: false`. Output shape:

```json
{"version": 1, "language": "en",
 "notice": "Advisory only, follow official INCOIS and IMD warnings.",
 "reachable": ["b0f0m0", "..."],
 "entries": {"b0f0m0": "text with {slots}", "...": "..."}}
```

`notice` is the per-language rendering of the mandatory advisory line. It lives at
the top level so Task 3's test can assert every reachable entry contains it,
rather than each language hard-coding its own copy in 40 places.

Fail loudly if an authored key is unreachable, if a reachable key is missing, or
if a slot name is not a `Capsule` attribute, a declared conversion, or a lexicon key.

- [ ] **Step 6: Implement `decode_reason` and `render`**

`decode_reason` applies the three cases from spec §6, using the `_SEVERITY` order
imported from `dhruva.risk.rules` rather than a second copy.

- [ ] **Step 7: Generate, run tests, confirm they pass**

```bash
.venv/bin/python -m dhruva.codec.generate_codebook
.venv/bin/python -m pytest backend/tests/test_codebook_render.py -q
```

- [ ] **Step 8: Add the determinism test**

Generated files are checked in, so they can drift from their source. This is the
test that stops that.

```python
# append to backend/tests/test_codebook_render.py
def test_generator_is_deterministic(tmp_path):
    """Regenerating must produce no diff. Checked-in build output is only safe
    if CI can prove it matches its source."""
    import pathlib, subprocess, filecmp
    before = {p.name: p.read_bytes() for p in pathlib.Path("data/codebook/build").glob("*.json")}
    subprocess.run(
        [".venv/bin/python", "-m", "dhruva.codec.generate_codebook"], check=True
    )
    after = {p.name: p.read_bytes() for p in pathlib.Path("data/codebook/build").glob("*.json")}
    assert before == after, "generator output drifted from the checked-in build"
```

- [ ] **Step 9: Commit**

```bash
git add data/codebook backend/dhruva/codec backend/tests/test_codebook_render.py
git commit -m "codec: add the English codebook and the degradation path"
```

---

### Task 3: Eleven more languages and the numeral tables

**Files:**
- Create: `data/codebook/lexicons/{ta,te,ml,kn,mr,kok,gu,or,bn,hi,ur}.yaml`
- Create: `data/codebook/templates/{ta,te,ml,kn,mr,kok,gu,or,bn,hi,ur}.yaml`
- Modify: `backend/dhruva/evidence/firewall.py` — extend `_WORD_NUMBERS`
- Test: `backend/tests/test_codebook_languages.py`

**Interfaces:**
- Consumes: the generator from Task 2.
- Produces: `data/codebook/build/<lang>.json` for all 12 languages.

- [ ] **Step 1: Write the failing test**

```python
# backend/tests/test_codebook_languages.py
import json, pathlib, re

LANGS = ["en", "ta", "te", "ml", "kn", "mr", "kok", "gu", "or", "bn", "hi", "ur"]
BUILD = pathlib.Path("data/codebook/build")


def test_twelve_languages_each_with_exactly_256_entries():
    assert sorted(p.stem for p in BUILD.glob("*.json")) == sorted(LANGS)
    for lang in LANGS:
        assert len(json.loads((BUILD / f"{lang}.json").read_text())["entries"]) == 256


def test_all_languages_share_one_key_set():
    keysets = {lang: set(json.loads((BUILD / f"{lang}.json").read_text())["entries"])
               for lang in LANGS}
    reference = keysets["en"]
    for lang, keys in keysets.items():
        assert keys == reference, f"{lang} key set differs"


def test_no_language_has_a_bare_digit_ascii_or_indic():
    for lang in LANGS:
        entries = json.loads((BUILD / f"{lang}.json").read_text())["entries"]
        for key, text in entries.items():
            stripped = re.sub(r"\{[a-z_]+\}", "", text)
            assert not any(ch.isdigit() for ch in stripped), f"{lang}:{key}"


def test_every_language_carries_the_advisory_notice_in_every_reachable_entry():
    for lang in LANGS:
        doc = json.loads((BUILD / f"{lang}.json").read_text())
        notice = doc["notice"]
        for key in doc["reachable"]:
            assert notice in doc["entries"][key], f"{lang}:{key} drops the notice"
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_codebook_languages.py -q`
Expected: FAIL — only `en.json` exists.

- [ ] **Step 3: Author the eleven lexicon files**

Same key set as `en.yaml`. Compass points in native script. This is the file where
a mistake sends a boat the wrong way — translate the point names, do not
transliterate the abbreviations.

- [ ] **Step 4: Author the eleven template files**

Same keys as `templates/en.yaml`. Keep sentences short and imperative: these are
spoken aloud over engine noise, not read. The advisory notice is mandatory in
every reachable entry.

- [ ] **Step 5: Extend `_WORD_NUMBERS` in `firewall.py`**

Add `te, ml, kn, mr, kok, gu, or, bn, ur` tables covering 0–10 and 100, matching
the existing `ta` and `hi` shape at `firewall.py:76`.

- [ ] **Step 6: Generate all twelve, run tests, confirm they pass**

```bash
.venv/bin/python -m dhruva.codec.generate_codebook
.venv/bin/python -m pytest backend/tests/test_codebook_languages.py -q
```

- [ ] **Step 7: Add the Python-side corpus render test**

The TypeScript side gets the same test in Task 6. Both must pass for the corpus
to mean anything as a contract.

```python
# append to backend/tests/test_codebook_languages.py
def test_every_corpus_capsule_renders_in_every_language():
    from dhruva.codec.codec import Capsule
    from dhruva.codec.codebook import render

    corpus = [json.loads(line) for line
              in pathlib.Path("eval/capsule_corpus.jsonl").read_text().splitlines()]
    assert len(corpus) == 500
    for row in corpus:
        capsule = Capsule(**row["capsule"])
        for lang in LANGS:
            text = render(capsule, lang)
            assert text, f"{row['id']}:{lang} rendered empty"
            assert not re.search(r"\{[a-z_]+\}", text), f"{row['id']}:{lang} has an unfilled slot"
```

- [ ] **Step 8: Commit**

```bash
git add data/codebook backend/dhruva/evidence/firewall.py backend/tests/test_codebook_languages.py
git commit -m "codec,evidence: add eleven languages and their numeral tables"
```

---

### Task 4: Wire node 9 and add QR transport

**Deviation from the original plan, found while implementing:** `codec.py`
already has `to_base32`/`from_base32`/`to_hex`/`from_hex` at the **bytes**
level (`to_base32(payload: bytes) -> str`), already exercised by
`TestTransports` in `test_codec.py` including a QR-alphanumeric-safety check.
Re-declaring `Capsule`-level functions of the same name in `qr.py` would shadow
tested code rather than extend it. Verified the corpus is consistent with them
first: encoding all 500 corpus capsules and comparing to their stored `hex` and
`base32` columns gives zero mismatches. What is actually still missing is (a) a
test that pins that consistency as a contract — nothing reads the corpus file
today — and (b) QR image generation, which does not exist in any form. Task
narrowed to just those two plus the node 9 wiring.

**Files:**
- Modify: `backend/tests/test_codec.py` — add the corpus-contract test
- Modify: `backend/dhruva/graph/build.py:395`
- Create: `backend/dhruva/codec/qr.py`
- Modify: `backend/pyproject.toml` — add `segno>=1.6` to the `data` extra
- Test: `backend/tests/test_qr.py`

**Interfaces:**
- Consumes: `reason_index` (Task 1), `encode`/`decode`/`to_base32`/`to_hex` from
  `dhruva.codec.codec` (existing, unmodified).
- Produces:
  - `qr_svg(capsule: Capsule, *, scale: int = 4) -> str`

- [ ] **Step 1: Write the failing corpus-contract test**

```python
# appended to backend/tests/test_codec.py
class TestCorpusContract:
    """eval/capsule_corpus.jsonl is the contract the TypeScript port is checked
    against. Pin here that the corpus agrees with THIS implementation, so a
    drift shows up on the Python side before it ever reaches TypeScript."""

    def test_every_corpus_row_matches_hex_and_base32(self):
        import json
        import pathlib

        rows = [
            json.loads(line)
            for line in pathlib.Path("eval/capsule_corpus.jsonl").read_text().splitlines()
        ]
        assert len(rows) == 500
        for row in rows:
            payload = encode(Capsule(**row["capsule"]))
            assert to_hex(payload) == row["hex"], row["id"]
            assert to_base32(payload) == row["base32"], row["id"]

    def test_every_corpus_row_round_trips_through_decode(self):
        import json
        import pathlib

        rows = [
            json.loads(line)
            for line in pathlib.Path("eval/capsule_corpus.jsonl").read_text().splitlines()
        ]
        for row in rows:
            original = Capsule(**row["capsule"])
            restored = decode(from_hex(row["hex"]))
            assert restored.as_dict() == original.as_dict(), row["id"]
```

- [ ] **Step 2: Run it and confirm it passes immediately**

Run: `.venv/bin/python -m pytest backend/tests/test_codec.py -k Corpus -v`
Expected: PASS — this pins existing, already-correct behaviour as a contract
rather than driving new code. If it fails, stop: the corpus and the encoder
have already drifted and that is a Task-1-through-3 regression, not a QR task.

- [ ] **Step 3: Write the failing QR test**

```python
# backend/tests/test_qr.py
import json
import pathlib

from dhruva.codec.codec import Capsule
from dhruva.codec.qr import qr_svg

CORPUS = [
    json.loads(line)
    for line in pathlib.Path("eval/capsule_corpus.jsonl").read_text().splitlines()
]


def test_qr_svg_is_emitted_and_self_contained():
    svg = qr_svg(Capsule(**CORPUS[0]["capsule"]))
    assert svg.lstrip().startswith("<?xml") or svg.lstrip().startswith("<svg")
    assert "http" not in svg


def test_qr_svg_is_deterministic():
    capsule = Capsule(**CORPUS[7]["capsule"])
    assert qr_svg(capsule) == qr_svg(capsule)


def test_every_corpus_capsule_produces_a_scannable_symbol():
    """segno raises if the payload does not fit the requested error-correction
    level, so this is really a size-budget check across the whole corpus."""
    for row in CORPUS[:50]:  # sampled: 500 segno encodes is slow, the format never changes per-row
        svg = qr_svg(Capsule(**row["capsule"]))
        assert svg
```

- [ ] **Step 4: Run it and confirm it fails**

Run: `.venv/bin/python -m pytest backend/tests/test_qr.py -q`
Expected: FAIL — `dhruva.codec.qr` not found.

- [ ] **Step 5: Add `segno` and implement `qr.py`**

```python
# backend/dhruva/codec/qr.py
"""QR transport for the capsule.

The wire format is identical across QR, Bluetooth and SMS (CLAUDE.md); this
module only adds the QR-specific step of turning the base32 string into a
scannable image. Encoding and the base32 alphabet themselves are unchanged —
see dhruva.codec.codec.to_base32 and its QR-alphanumeric-safety test.
"""

from __future__ import annotations

import segno

from dhruva.codec.codec import Capsule, encode, to_base32


def qr_svg(capsule: Capsule, *, scale: int = 4) -> str:
    """An SVG string, no filesystem write. Alphanumeric mode: to_base32 already
    guarantees an uppercase, digit-and-A-Z-only alphabet, so segno never falls
    back to the denser byte mode."""
    payload = to_base32(encode(capsule))
    qr = segno.make(payload, error="m")
    import io

    buf = io.StringIO()
    qr.save(buf, kind="svg", scale=scale, xmldecl=True)
    return buf.getvalue()
```

Add to `backend/pyproject.toml`'s `data` extra: `"segno>=1.6",` then
`uv pip install -e "backend[data]"` (or `pip install segno` directly into
`.venv` if `uv` is not driving this shell).

- [ ] **Step 6: Run it and confirm it passes**

Run: `.venv/bin/python -m pytest backend/tests/test_qr.py backend/tests/test_codec.py -q`
Expected: all pass.

- [ ] **Step 7: Replace the node 9 stub**

At `build.py:395`, delete `{RiskClass.SAFE: 1, RiskClass.CAUTION: 41, RiskClass.NO_GO: 90}`
and call `reason_index(assess(state), capsule)`. Node 9 also builds the capsule
and returns `base32` on the state.

- [ ] **Step 8: Run the full suite and confirm it passes**

Run: `.venv/bin/python -m pytest backend/tests -q`
Expected: all green, 273 (post Task 3) + new tests.

- [ ] **Step 9: Run the capsule-auditor subagent**

CLAUDE.md requires it after every codec change.

- [ ] **Step 10: Commit**

```bash
git add backend/ && git commit -m "codec,graph: add QR transport and wire the reason index into node 9"
```

---

### Task 5: Frontend scaffold and the TypeScript decoder port

**Files:**
- Create: `frontend/package.json`, `frontend/vite.config.ts`, `frontend/tsconfig.json`
- Create: `frontend/src/shared/capsule/fields.ts`
- Create: `frontend/src/shared/capsule/decode.ts`
- Test: `frontend/src/shared/capsule/decode.test.ts`

**Interfaces:**
- Consumes: `eval/capsule_corpus.jsonl` — the contract.
- Produces:
  - `decodeCapsule(base32: string): Capsule`
  - `decodeHex(hex: string): Capsule`
  - `FIELDS: readonly Field[]` mirroring `fields.py`

- [ ] **Step 1: Scaffold the project**

```bash
cd frontend && npm create vite@latest . -- --template react-ts && npm i && npm i -D vitest
```

Add `"test": "vitest run"` to `package.json` scripts.

- [ ] **Step 2: Write the failing test**

```typescript
// frontend/src/shared/capsule/decode.test.ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { decodeCapsule, decodeHex } from "./decode";

const corpus = readFileSync("../eval/capsule_corpus.jsonl", "utf8")
  .trim().split("\n").map((l) => JSON.parse(l));

describe("capsule decoder parity", () => {
  it("decodes every corpus capsule from base32 identically to Python", () => {
    for (const row of corpus) {
      expect(decodeCapsule(row.base32)).toEqual(row.capsule);
    }
  });

  it("decodes every corpus capsule from hex identically to Python", () => {
    for (const row of corpus) {
      expect(decodeHex(row.hex)).toEqual(row.capsule);
    }
  });

  it("is pure — no network, filesystem or clock", () => {
    const src = readFileSync("src/shared/capsule/decode.ts", "utf8");
    for (const banned of ["fetch(", "Date.now", "new Date", "require(", "localStorage"]) {
      expect(src).not.toContain(banned);
    }
  });
});
```

- [ ] **Step 3: Run it and confirm it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `./decode` not found.

- [ ] **Step 4: Generate `fields.ts` from `fields.py`**

Add a `--emit-ts` flag to `generate_codebook.py`, or a sibling script, that writes
`fields.ts` from the same `FIELDS` tuple. Generated, never hand-edited — that is
what stops the two implementations drifting.

- [ ] **Step 5: Implement `decode.ts`**

MSB-first bit reader over a `Uint8Array`. Mirror `codec.py`'s `from_raw` exactly,
including `scale` and `offset` handling. JavaScript numbers are doubles, so apply
the same rounding the Python side uses rather than trusting float equality.

- [ ] **Step 6: Run tests and confirm they pass**

Run: `cd frontend && npm test`
Expected: 3 passing, 500 capsules each.

- [ ] **Step 7: Commit**

```bash
git add frontend/ && git commit -m "frontend: port the capsule decoder to TypeScript"
```

---

### Task 6: TypeScript codebook render and CI parity

**Files:**
- Create: `frontend/src/shared/capsule/codebook.ts`
- Test: `frontend/src/shared/capsule/codebook.test.ts`
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Consumes: `decodeCapsule` (Task 5), `data/codebook/build/<lang>.json` (Task 3).
- Produces: `renderReason(capsule: Capsule, language: string): { text: string; degraded: boolean }`

- [ ] **Step 1: Write the failing test**

```typescript
// frontend/src/shared/capsule/codebook.test.ts
import { describe, it, expect } from "vitest";
import { readFileSync } from "node:fs";
import { renderReason } from "./codebook";

const corpus = readFileSync("../eval/capsule_corpus.jsonl", "utf8")
  .trim().split("\n").map((l) => JSON.parse(l));
const LANGS = ["en","ta","te","ml","kn","mr","kok","gu","or","bn","hi","ur"];

describe("codebook render", () => {
  it("renders every corpus capsule in all twelve languages with no unfilled slots", () => {
    for (const row of corpus) {
      for (const lang of LANGS) {
        const out = renderReason(row.capsule, lang);
        expect(out.text.length).toBeGreaterThan(0);
        expect(out.text).not.toMatch(/\{[a-z_]+\}/);
      }
    }
  });

  it("degrades to the worse band when reason_code disagrees with risk_class", () => {
    const capsule = { ...corpus[0].capsule, risk_class: "no-go", reason_code: 0b00_001_000 };
    expect(renderReason(capsule, "en").degraded).toBe(true);
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `./codebook` not found.

- [ ] **Step 3: Implement `codebook.ts`**

Import the 12 JSON files statically so the bundler includes them — the decoder is
pure and cannot read the filesystem at runtime. Mirror `decode_reason`'s three
cases and the `_SEVERITY` order exactly.

- [ ] **Step 4: Add a cross-language parity test**

A test that renders all 500 capsules in Python and in TypeScript and asserts the
strings are byte-identical. Emit the Python side to a JSON file in a pytest run,
read it from vitest.

- [ ] **Step 5: Add the frontend job to CI**

```yaml
  frontend:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: {node-version: '22', cache: npm, cache-dependency-path: frontend/package-lock.json}
      - run: npm ci
        working-directory: frontend
      - run: npm run test
        working-directory: frontend
```

- [ ] **Step 6: Run both suites and confirm they pass**

```bash
.venv/bin/python -m pytest backend/tests -q && (cd frontend && npm test)
```

- [ ] **Step 7: Commit**

```bash
git add frontend/ .github/workflows/ci.yml
git commit -m "frontend,ci: render the codebook in TypeScript and check parity"
```

---

### Task 7: Scan and speak

**Files:**
- Create: `frontend/src/boat/ScanView.tsx`
- Modify: `frontend/package.json` — add `jsqr`
- Test: `frontend/src/boat/ScanView.test.tsx`

**Interfaces:**
- Consumes: `decodeCapsule`, `renderReason`.
- Produces: a route that opens the camera, decodes a QR, and speaks the result.

- [ ] **Step 1: Write the failing test**

```tsx
// frontend/src/boat/ScanView.test.tsx
import { describe, it, expect, vi } from "vitest";
import { advisoryFor } from "./ScanView";

describe("advisoryFor", () => {
  it("turns a scanned base32 payload into spoken Tamil text", () => {
    const out = advisoryFor("BRWZQC75355GADBL7ASLYXG7BEJGKAA", "ta");
    expect(out.text.length).toBeGreaterThan(0);
    expect(out.text).not.toMatch(/\{[a-z_]+\}/);
  });

  it("rejects a payload of the wrong length rather than decoding garbage", () => {
    expect(() => advisoryFor("TOOSHORT", "ta")).toThrow();
  });
});
```

- [ ] **Step 2: Run it and confirm it fails**

Run: `cd frontend && npm test`
Expected: FAIL — `./ScanView` not found.

- [ ] **Step 3: Implement `ScanView.tsx`**

`advisoryFor(payload, lang)` is pure and exported separately from the component so
it is testable without a camera. The component wires `getUserMedia` → `jsQR` →
`advisoryFor` → `speechSynthesis`. Show the `degraded` flag visibly when set.

- [ ] **Step 4: Add the offline speech path**

`speechSynthesis` with a Tamil voice works offline where the OS ships one. Where
it does not, the PWA falls back to a pre-rendered Sarvam Bulbul v3 clip cached by
the service worker per reachable codebook entry. Record which path the demo device
takes — this is the difference between the gate passing and appearing to pass.

- [ ] **Step 5: Run both suites and confirm they pass**

```bash
.venv/bin/python -m pytest backend/tests -q && (cd frontend && npm test)
```

- [ ] **Step 6: Commit**

```bash
git add frontend/ && git commit -m "frontend: scan a capsule QR and speak the advisory"
```

---

## Gate 4 verification — needs a human and a phone

Everything above is machine-checkable. The gate itself is not:

1. Serve the PWA over HTTPS (the camera needs a secure context — Caddy on `:8081` already terminates TLS).
2. Install it on an Android phone, open it once so the service worker caches.
3. Put the phone in **airplane mode**. Confirm the radio is actually off.
4. Scan a QR rendered by `qr_svg()` for a Tamil demo capsule.
5. Confirm it speaks a full Tamil advisory, and that the advisory notice is spoken.

Record the outcome in `docs/STATUS.md`. Until step 5 is observed on a real device,
Gate 4 is **not** passed, however green CI is.
