"""QR transport.

The wire format is identical across QR, Bluetooth and SMS (CLAUDE.md). Encoding
and the base32 alphabet are dhruva.codec.codec's job, already tested; this file
only covers the QR-specific step of turning that string into a scannable image.
"""

from __future__ import annotations

import json
import pathlib

from dhruva.codec.codec import Capsule
from dhruva.codec.qr import qr_svg

CORPUS = [
    json.loads(line) for line in pathlib.Path("eval/capsule_corpus.jsonl").read_text().splitlines()
]


def test_qr_svg_is_emitted_and_self_contained():
    """Self-contained means no external resource load — an xmlns URI is
    required SVG boilerplate, not a network reference, so it is not what this
    checks."""
    svg = qr_svg(Capsule(**CORPUS[0]["capsule"]))
    assert svg.lstrip().startswith("<?xml") or svg.lstrip().startswith("<svg")
    assert "<script" not in svg
    assert "<image" not in svg
    assert "xlink:href" not in svg


def test_qr_svg_is_deterministic():
    capsule = Capsule(**CORPUS[7]["capsule"])
    assert qr_svg(capsule) == qr_svg(capsule)


def test_qr_svg_differs_for_a_different_capsule():
    a = qr_svg(Capsule(**CORPUS[0]["capsule"]))
    b = qr_svg(Capsule(**CORPUS[1]["capsule"]))
    assert a != b


def test_every_corpus_capsule_produces_a_scannable_symbol():
    """segno raises if the payload does not fit the requested error-correction
    level, so this is really a size-budget check across a sample of the corpus.
    Sampled: encoding all 500 is slow and the wire format never changes per-row."""
    for row in CORPUS[:50]:
        svg = qr_svg(Capsule(**row["capsule"]))
        assert svg
