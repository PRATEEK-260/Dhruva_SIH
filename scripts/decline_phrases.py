#!/usr/bin/env python
"""Translate query #7's sentences (data/phrases/decline.json) with Bhashini.

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
    PYTHONPATH=backend .venv/bin/python scripts/decline_phrases.py
"""

from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path

import httpx
from dhruva.lang import bhashini

LANGUAGES = ("ta", "ml", "or", "hi")
ROOT = Path(__file__).resolve().parent.parent
PATH = ROOT / "data/phrases/decline.json"
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


async def main() -> None:
    key = os.environ["BHASHINI_INFERENCE_API_KEY"]
    table = json.loads(PATH.read_text(encoding="utf-8"))
    en: dict[str, str] = table["en"]
    failed = []
    async with httpx.AsyncClient() as client:
        for lang in LANGUAGES:
            out = table.setdefault(lang, {})
            source = out.setdefault("_en", {})
            for k, sentence in en.items():
                if source.get(k) == sentence and k in out:
                    continue
                protected, tokens = _protect(sentence)
                raw = await bhashini.translate(client, key, protected, "en", lang)
                text = _restore(raw, tokens)
                if text is None:
                    failed.append(f"{lang}.{k}: {raw}")
                    print(f"{lang} {k:<22} FAILED  {raw}")
                    continue
                out[k], source[k] = text, sentence
                print(f"{lang} {k:<22} {text}")
    PATH.write_text(json.dumps(table, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {PATH.relative_to(ROOT)}")
    if failed:
        print("\nNot written, fix by hand:\n  " + "\n  ".join(failed))


if __name__ == "__main__":
    asyncio.run(main())
