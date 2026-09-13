"""Twelve languages, one key set, no invented numbers.

Gate 4 requires exactly 256 entries rendering in all twelve. These tests hold the
shape; whether the Tamil actually reads well to a Tamil speaker is a review these
tests cannot perform, and docs/STATUS.md says so.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

from dhruva.codec.codebook import load_codebook, render
from dhruva.codec.codec import Capsule
from dhruva.codec.generate_codebook import LANGUAGES

BUILD = pathlib.Path("data/codebook/build")
SLOT = re.compile(r"\{[a-z_]+\}")
# Devanagari danda, Bengali/Odia danda and the Urdu full stop are sentence
# terminators too. Splitting only on "." would silently skip nine languages.
TERMINATORS = re.compile(r"[.।۔॥]")  # noqa: RUF001 — the Urdu full stop is deliberate


def _entries(language: str) -> dict[str, str]:
    return json.loads((BUILD / f"{language}.json").read_text(encoding="utf-8"))["entries"]


def test_twelve_languages_are_built() -> None:
    assert sorted(p.stem for p in BUILD.glob("*.json")) == sorted(LANGUAGES)
    assert len(LANGUAGES) == 12


@pytest.mark.parametrize("language", LANGUAGES)
def test_each_language_has_exactly_256_entries(language: str) -> None:
    assert len(_entries(language)) == 256


def test_all_languages_share_one_key_set() -> None:
    reference = set(_entries("en"))
    for language in LANGUAGES:
        assert set(_entries(language)) == reference, f"{language} key set differs"


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_bare_digit_ascii_or_indic(language: str) -> None:
    """The numeric firewall, enforced statically across every script."""
    for key, text in _entries(language).items():
        stripped = SLOT.sub("", text)
        offenders = [ch for ch in stripped if ch.isdigit()]
        assert not offenders, f"{language}:{key} contains {offenders!r}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_every_reachable_entry_carries_the_advisory_notice(language: str) -> None:
    doc = json.loads((BUILD / f"{language}.json").read_text(encoding="utf-8"))
    for key in doc["reachable"]:
        assert doc["notice"] in doc["entries"][key], f"{language}:{key} drops the notice"


@pytest.mark.parametrize("language", LANGUAGES)
def test_no_entry_repeats_a_sentence_in_any_script(language: str) -> None:
    for key, text in _entries(language).items():
        sentences = [s.strip() for s in TERMINATORS.split(text) if s.strip()]
        repeated = {s for s in sentences if sentences.count(s) > 1}
        assert not repeated, f"{language}:{key} repeats {repeated}"


@pytest.mark.parametrize("language", LANGUAGES)
def test_lexicon_has_all_sixteen_compass_points(language: str) -> None:
    from dhruva.codec.codebook import load_lexicon

    lexicon = load_lexicon(language)
    assert set(lexicon["compass"]) == set(range(16)), f"{language} compass incomplete"
    for index, name in lexicon["compass"].items():
        assert name.strip(), f"{language} compass {index} is blank"


def test_every_corpus_capsule_renders_in_every_language() -> None:
    """The 500-capsule corpus is the contract. If it renders here it must render
    identically in TypeScript, which Task 6 checks."""
    corpus = [
        json.loads(line)
        for line in pathlib.Path("eval/capsule_corpus.jsonl").read_text().splitlines()
    ]
    assert len(corpus) == 500
    for row in corpus:
        capsule = Capsule(**row["capsule"])
        for language in LANGUAGES:
            text = render(capsule, language)
            assert text, f"{row['id']}:{language} rendered empty"
            assert not SLOT.search(text), f"{row['id']}:{language} left a slot unfilled"


def test_notice_differs_per_language_rather_than_falling_back_to_english() -> None:
    """A silently untranslated notice would ship English text to a Tamil crew."""
    notices = {language: load_codebook(language)["notice"] for language in LANGUAGES}
    non_english = {lang: n for lang, n in notices.items() if lang != "en"}
    assert notices["en"] not in non_english.values()
    assert len(set(non_english.values())) == len(non_english)


def test_firewall_knows_spelled_out_numerals_in_all_twelve_languages() -> None:
    """Without a table the validator cannot see a spelled-out number, so a model
    could smuggle one past it in nine of the twelve languages."""
    from dhruva.evidence.firewall import _WORD_NUMBERS

    for language in LANGUAGES:
        table = _WORD_NUMBERS.get(language)
        assert table, f"{language} has no spelled-out numeral table"
        assert set(table.values()) >= set(range(11)), f"{language} missing 0-10"
