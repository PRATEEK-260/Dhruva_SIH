#!/usr/bin/env python
"""Translate the answer sentences (data/phrases/*.json) with Bhashini.

Placeholders do not survive machine translation reliably, so each {name} goes
in as a number token MT leaves alone (701, 702, ...) and comes back out. A
sentence whose tokens do not all come back exactly once is not written: it is
reported, and the English line stays the source of truth until it is fixed by
hand.

Like scripts/verdict_labels.py, it translates only what is missing or whose
English changed, so a line a native speaker corrected by hand is kept.
Machine translation: a native speaker should check every line before any
public claim.

    set -a; . ./.env; set +a
    PYTHONPATH=backend .venv/bin/python scripts/phrases.py [kind ...]

A nested table (country names, storm categories) is translated entry by entry.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
from pathlib import Path

import httpx
from dhruva.lang import bhashini

LANGUAGES = ("ta", "ml", "or", "hi")
ROOT = Path(__file__).resolve().parent.parent
PHRASES = ROOT / "data/phrases"
_PLACEHOLDER = re.compile(r"{(\w+)}")


def _protect(sentence: str) -> tuple[str, dict[str, str]]:
    tokens: dict[str, str] = {}

    def swap(m: re.Match[str]) -> str:
        token = str(701 + len(tokens))
        tokens[token] = m.group(0)
        return token

    return _PLACEHOLDER.sub(swap, sentence), tokens


def _restore(text: str, tokens: dict[str, str]) -> str | None:
    for token, placeholder in tokens.items():
        if len(re.findall(rf"(?<!\d){token}(?!\d)", text)) != 1:
            return None
        text = re.sub(rf"(?<!\d){token}(?!\d)", placeholder, text)
    # MT sometimes writes the token in the script's own digits; those are not
    # restored above, so any leftover digit means a token was mangled.
    if re.search(r"\d", _PLACEHOLDER.sub("", text)):
        return None
    return text


async def _one(client, key: str, sentence: str, lang: str, failed: list[str], label: str):
    protected, tokens = _protect(sentence)
    raw = await bhashini.translate(client, key, protected, "en", lang)
    text = _restore(raw, tokens)
    if text is None:
        failed.append(f"{label}: {raw}")
        print(f"{label:<34} FAILED  {raw}")
    else:
        print(f"{label:<34} {text}")
    return text


async def translate_file(client, key: str, path: Path, failed: list[str]) -> None:
    """Translates what is missing or whose English changed, so a line a
    native speaker corrected by hand is kept."""
    table = json.loads(path.read_text(encoding="utf-8"))
    en: dict = table["en"]
    for lang in LANGUAGES:
        out = table.setdefault(lang, {})
        source = out.setdefault("_en", {})
        for k, value in en.items():
            if isinstance(value, dict):
                sub_out = out.setdefault(k, {})
                sub_src = source.setdefault(k, {})
                for w, word in value.items():
                    if sub_src.get(w) == word and w in sub_out:
                        continue
                    t = await _one(client, key, word, lang, failed, f"{path.stem}.{lang}.{k}.{w}")
                    if t is not None:
                        sub_out[w], sub_src[w] = t.rstrip("."), word
                continue
            if source.get(k) == value and k in out:
                continue
            t = await _one(client, key, value, lang, failed, f"{path.stem}.{lang}.{k}")
            if t is not None:
                out[k], source[k] = t, value
    path.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


async def main() -> None:
    key = os.environ["BHASHINI_INFERENCE_API_KEY"]
    kinds = sys.argv[1:] or sorted(p.stem for p in PHRASES.glob("*.json"))
    failed: list[str] = []
    async with httpx.AsyncClient() as client:
        for kind in kinds:
            await translate_file(client, key, PHRASES / f"{kind}.json", failed)
    if failed:
        print("\nNot written, fix by hand:\n  " + "\n  ".join(failed))


if __name__ == "__main__":
    asyncio.run(main())
