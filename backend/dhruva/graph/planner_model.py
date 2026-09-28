"""The planner's model: Gemini, called directly on its OpenAI-compatible endpoint.

It does one thing — pick which of the eight PS question types a query is — and
its output is constrained to that enum by a JSON schema, then checked again
here. It writes no narration and emits no number, so nothing it says can reach
the fisherman; the worst a wrong answer can do is fetch the wrong variables.

Every failure (no key, rejected key, timeout, malformed or off-contract output)
returns an intent of None with the reason, and the planner node falls back to
the keyword classifier. The graph never stops because a model did.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass

import httpx

from dhruva.graph.state import Intent

GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"

# Flash-Lite, not Flash: picking one of eight labels does not need the bigger
# model, and on 2026-09-28 gemini-3.8-flash was answering 503 under load while
# Lite answered in about 1.3 s. gemini-2.5-flash is closed to new API keys.
MODEL = os.environ.get("DHRUVA_PLANNER_MODEL", "gemini-3.5-flash-lite")

# The planner sits in front of the 3000 ms gate budget; a slow model call is
# worth less than the keyword answer it delays.
TIMEOUT_S = 8.0

SYSTEM_PROMPT = """\
You route questions from Indian fishermen to one of eight question types.
Questions may be in English or any Indian language; classify by meaning, not
keywords. Answer with the type only.

go_no_go: whether it is safe or advisable to go out, or to stay out, now or at a stated time.
fishing_zone: where to find fish, potential fishing zones (PFZ), good spots to fish.
route: how to get somewhere at sea: route, course, safest way to a place or back to harbour.
boundary: maritime boundaries, the IMBL, EEZ, protected areas, which side of a line.
hazard: warnings and alerts: cyclone, storm, lightning, tsunami, high-wave alerts.
conditions: current or forecast sea state and weather: waves, wind, current, water temperature.
decline_attribution: why the sea or the catch has changed over time, e.g. why fish have declined.
explain: questions about this system's own answer: why it said something, its data or rules.

If a safety question mentions fishing, it is go_no_go. If a question names a
destination but asks how to get there, it is route."""


@dataclass(frozen=True)
class ModelChoice:
    """What the model decided, or None and why it could not."""

    intent: Intent | None
    reason: str


def _request_body(query: str, model: str) -> dict:
    return {
        "model": model,
        "temperature": 0,
        "max_tokens": 50,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": query},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "route",
                "strict": True,
                "schema": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string", "enum": [i.value for i in Intent]},
                    },
                    "required": ["intent"],
                    "additionalProperties": False,
                },
            },
        },
    }


def _parse(payload: dict) -> Intent | None:
    """The schema asks for the enum; this refuses anything that slipped past it
    rather than guessing what the model meant."""
    try:
        content = payload["choices"][0]["message"]["content"]
        return Intent(json.loads(content)["intent"])
    except (KeyError, IndexError, TypeError, ValueError):
        return None


async def classify_with_model(
    query: str,
    *,
    api_key: str | None,
    client: httpx.AsyncClient | None = None,
    model: str = MODEL,
) -> ModelChoice:
    if not api_key:
        return ModelChoice(None, "no GEMINI_API_KEY")

    owned = client is None
    http = client or httpx.AsyncClient()
    try:
        response = await http.post(
            GEMINI_URL,
            json=_request_body(query, model),
            headers={"Authorization": f"Bearer {api_key}"},
            timeout=TIMEOUT_S,
        )
    except httpx.HTTPError as exc:
        return ModelChoice(None, f"gemini unreachable: {type(exc).__name__}")
    finally:
        if owned:
            await http.aclose()

    if response.status_code != 200:
        return ModelChoice(None, f"gemini answered {response.status_code}")
    try:
        intent = _parse(response.json())
    except ValueError:
        intent = None
    if intent is None:
        return ModelChoice(None, "model output outside the intent contract")
    return ModelChoice(intent, f"model {model} chose {intent.value}")
