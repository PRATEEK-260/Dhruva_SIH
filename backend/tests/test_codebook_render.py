"""Degradation and rendering.

The decoder is what a phone runs with its radio off, so these tests care most
about what happens when the byte arrives damaged. A wrong sentence is worse than
a vague one.
"""

from __future__ import annotations

import json
import pathlib
import re

from dhruva.codec.codebook import decode_reason, join_reason, render
from dhruva.codec.codec import Capsule

BUILD = pathlib.Path("data/codebook/build")
SLOT = re.compile(r"\{[a-z_]+\}")


def test_coherent_code_renders_its_own_entry() -> None:
    code = join_reason(2, 1, 1)  # no_go, wave, saturated
    out = decode_reason(code, risk_class=2)
    assert not out.degraded
    assert (out.band, out.family, out.modifier) == (2, 1, 1)
    assert out.text


def test_mismatch_takes_the_worse_band_and_goes_generic() -> None:
    code = join_reason(0, 1, 0)  # the byte claims safe
    out = decode_reason(code, risk_class=2)  # the capsule says no_go
    assert out.degraded
    assert out.band == 2
    assert (out.family, out.modifier) == (0, 0)


def test_mismatch_between_safe_and_unknown_resolves_to_unknown() -> None:
    """UNKNOWN outranks SAFE in _SEVERITY: not knowing is worse than fine."""
    out = decode_reason(join_reason(0, 1, 0), risk_class=3)
    assert out.degraded
    assert out.band == 3


def test_mismatch_prefers_no_go_over_caution() -> None:
    out = decode_reason(join_reason(1, 1, 0), risk_class=2)
    assert out.degraded
    assert out.band == 2


def test_unreachable_but_coherent_code_degrades_to_generic() -> None:
    code = join_reason(0, 5, 0)  # tsunami in the safe band
    out = decode_reason(code, risk_class=0)
    assert out.degraded
    assert (out.family, out.modifier) == (0, 0)


def test_every_band_has_a_generic_entry_to_degrade_into() -> None:
    for band in range(4):
        out = decode_reason(join_reason(band, 7, 7), risk_class=band)
        assert out.text, f"band {band} has no generic entry"


def test_render_fills_every_slot() -> None:
    capsule = Capsule(risk_class="no_go", reason_code=join_reason(2, 1, 0), wave_hs_m=4.5)
    text = render(capsule, "en")
    assert text
    assert not SLOT.search(text), f"unfilled slot in: {text}"


def test_render_speaks_a_saturated_reading_as_at_least() -> None:
    """A railed value quoted as exact is the specific lie the spec forbids."""
    capsule = Capsule(risk_class="no_go", reason_code=join_reason(2, 1, 1), wave_hs_m=7.75)
    text = render(capsule, "en")
    assert "at least" in text.lower()


def test_no_template_contains_a_literal_digit_outside_a_slot() -> None:
    """The numeric firewall, enforced statically. A hardcoded number in a
    template is a number with no evidence behind it."""
    for path in BUILD.glob("*.json"):
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
        for key, text in entries.items():
            stripped = SLOT.sub("", text)
            assert not any(ch.isdigit() for ch in stripped), f"{path.name}:{key} -> {text}"


def test_build_has_exactly_256_entries() -> None:
    doc = json.loads((BUILD / "en.json").read_text(encoding="utf-8"))
    assert len(doc["entries"]) == 256


def test_generator_is_deterministic() -> None:
    """Generated files are checked in, so they can drift from their source."""
    import subprocess

    before = {p.name: p.read_bytes() for p in BUILD.glob("*.json")}
    subprocess.run(
        [".venv/bin/python", "-m", "dhruva.codec.generate_codebook"],
        check=True,
        capture_output=True,
    )
    after = {p.name: p.read_bytes() for p in BUILD.glob("*.json")}
    assert before == after, "generator output drifted from the checked-in build"


def test_no_entry_repeats_a_sentence() -> None:
    """Composition can make the band opener and the evidence say the same thing
    twice. Spoken aloud that sounds like a fault, so it is a test, not a habit."""
    for path in BUILD.glob("*.json"):
        entries = json.loads(path.read_text(encoding="utf-8"))["entries"]
        for key, text in entries.items():
            sentences = [s.strip() for s in text.split(".") if s.strip()]
            duplicates = {s for s in sentences if sentences.count(s) > 1}
            assert not duplicates, f"{path.name}:{key} repeats {duplicates}"
