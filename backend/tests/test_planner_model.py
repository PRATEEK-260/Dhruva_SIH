"""Node 0 with a model behind it — Gemini, called directly.

The model only ever picks one of the eight intents. It never writes narration
here and never emits a number, so the firewall is not in play; what matters is
that every way the call can go wrong lands on the keyword classifier instead of
on a crashed graph or a made-up intent.

Gemini's OpenAI-compatible endpoint is the one thing mocked, at the HTTP
transport. Response bodies mirror its real chat-completions shape.
"""

import asyncio
import json
import os
import time

import httpx
import pytest

from dhruva.graph import planner_model
from dhruva.graph.build import planner
from dhruva.graph.planner_model import classify_with_model
from dhruva.graph.state import Intent, initial_state

ALL_INTENTS = {
    "go_no_go",
    "fishing_zone",
    "route",
    "boundary",
    "hazard",
    "conditions",
    "decline_attribution",
    "explain",
}


def _completion(content: str) -> dict:
    return {
        "id": "7K0nZ-abcDEF",
        "model": "gemini-3.5-flash-lite",
        "object": "chat.completion",
        "created": 1727500000,
        "choices": [
            {
                "finish_reason": "stop",
                "index": 0,
                "message": {"role": "assistant", "content": content},
            }
        ],
        "usage": {"prompt_tokens": 412, "completion_tokens": 9, "total_tokens": 421},
    }


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


class TestClassifyWithModel:
    async def test_the_models_intent_is_returned(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion('{"intent": "hazard"}'))

        async with _client(handler) as client:
            choice = await classify_with_model("Any storm tonight?", api_key="k", client=client)

        assert choice.intent is Intent.HAZARD

    async def test_the_request_pins_the_model_and_constrains_output_to_the_eight_intents(self):
        seen: dict = {}

        def handler(request: httpx.Request) -> httpx.Response:
            seen["url"] = str(request.url)
            seen["auth"] = request.headers.get("authorization")
            seen["body"] = json.loads(request.content)
            return httpx.Response(200, json=_completion('{"intent": "route"}'))

        async with _client(handler) as client:
            await classify_with_model("Safest way home?", api_key="gm-test", client=client)

        body = seen["body"]
        assert (
            seen["url"]
            == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
        )
        assert seen["auth"] == "Bearer gm-test"
        assert body["model"] == "gemini-3.5-flash-lite"
        assert body["temperature"] == 0
        schema = body["response_format"]["json_schema"]["schema"]
        assert set(schema["properties"]["intent"]["enum"]) == ALL_INTENTS
        assert "Safest way home?" in body["messages"][-1]["content"]

    async def test_no_key_means_no_request_and_no_intent(self):
        calls = []

        def handler(request: httpx.Request) -> httpx.Response:
            calls.append(request)
            return httpx.Response(200, json=_completion('{"intent": "hazard"}'))

        async with _client(handler) as client:
            choice = await classify_with_model("Any storm?", api_key=None, client=client)

        assert choice.intent is None
        assert calls == []

    async def test_a_rejected_key_gives_no_intent_and_says_why(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json=[
                    {
                        "error": {
                            "code": 401,
                            "message": "API key not valid.",
                            "status": "UNAUTHENTICATED",
                        }
                    }
                ],
            )

        async with _client(handler) as client:
            choice = await classify_with_model("Any storm?", api_key="bad", client=client)

        assert choice.intent is None
        assert "401" in choice.reason

    async def test_a_timeout_gives_no_intent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            raise httpx.ReadTimeout("slow", request=request)

        async with _client(handler) as client:
            choice = await classify_with_model("Any storm?", api_key="k", client=client)

        assert choice.intent is None

    @pytest.mark.parametrize(
        "content",
        [
            "hazard",  # not JSON
            '{"intent": "weather_report"}',  # not one of the eight
            '{"label": "hazard"}',  # wrong key
            "",  # empty
        ],
    )
    async def test_output_outside_the_contract_is_refused_not_guessed(self, content):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=_completion(content))

        async with _client(handler) as client:
            choice = await classify_with_model("Any storm?", api_key="k", client=client)

        assert choice.intent is None

    async def test_a_response_with_no_choices_gives_no_intent(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"id": "gen-1", "choices": []})

        async with _client(handler) as client:
            choice = await classify_with_model("Any storm?", api_key="k", client=client)

        assert choice.intent is None


class TestPlannerNode:
    async def test_the_model_decides_when_it_answers(self, monkeypatch):
        """The keyword scorer reads "Any storm tonight?" as HAZARD too, so use a
        query where they disagree: no keyword signal at all falls back to
        CONDITIONS, and the model's EXPLAIN must win."""

        async def fake(query, *, api_key, **_):
            assert api_key == "k", "planner must read GEMINI_API_KEY"
            return planner_model.ModelChoice(Intent.EXPLAIN, "model gemini-3.5-flash-lite")

        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setattr("dhruva.graph.build.classify_with_model", fake)

        out = await planner(initial_state("zzzz qqqq", 11.05, 79.95))

        assert out["intent"] is Intent.EXPLAIN
        assert out["plan"]["nodes"] == ["discovery"]
        assert "model" in out["plan"]["reason"]

    async def test_the_keyword_classifier_takes_over_when_the_model_cannot_answer(
        self, monkeypatch
    ):
        async def fake(query, *, api_key, **_):
            return planner_model.ModelChoice(None, "gemini answered 401")

        monkeypatch.setenv("GEMINI_API_KEY", "k")
        monkeypatch.setattr("dhruva.graph.build.classify_with_model", fake)

        out = await planner(initial_state("Is there a cyclone warning?", 11.05, 79.95))

        assert out["intent"] is Intent.HAZARD
        assert out["plan"]["nodes"] == ["discovery", "weather", "geo"]
        assert "keyword" in out["plan"]["reason"]
        assert "401" in out["plan"]["reason"]


LIVE = os.environ.get("DHRUVA_LIVE_LLM") == "1" and bool(os.environ.get("GEMINI_API_KEY"))


@pytest.mark.skipif(not LIVE, reason="set DHRUVA_LIVE_LLM=1 and GEMINI_API_KEY")
class TestLiveGate3b:
    """The honest routing number. Unlike classify(), the model was never tuned
    on eval/queries.jsonl, so this is a generalisation estimate rather than an
    upper bound. Costs one short call per query.

    The free tier allows 15 requests a minute per model, so calls are paced;
    unpaced, everything after the fifteenth answers 429. DHRUVA_LIVE_PACE_S=0
    on a paid key."""

    async def test_model_routing_meets_the_target(self):
        from tests.test_routing import CASES, TARGET

        key = os.environ["GEMINI_API_KEY"]
        pace = float(os.environ.get("DHRUVA_LIVE_PACE_S", "4.5"))
        misses, unanswered, elapsed_ms = [], [], []
        async with httpx.AsyncClient() as client:
            for c in CASES:
                await asyncio.sleep(pace)
                start = time.perf_counter()
                choice = await classify_with_model(c["query"], api_key=key, client=client)
                elapsed_ms.append((time.perf_counter() - start) * 1000)
                if choice.intent is None:
                    unanswered.append(f"{c['id']}: {choice.reason}")
                elif choice.intent.value != c["expected_intent"]:
                    misses.append(
                        f"{c['id']}: {c['query'][:40]!r} expected "
                        f"{c['expected_intent']} got {choice.intent.value}"
                    )

        # A call the model could not answer is routed by the keyword fallback in
        # production, so it is reported, not scored against the model. It is
        # bounded, though: a model that mostly times out is not being measured.
        answered = len(CASES) - len(unanswered)
        accuracy = 1 - len(misses) / answered if answered else 0.0
        ms = sorted(elapsed_ms)
        report = "\n".join(
            [
                f"model routing {accuracy:.1%} on {answered} answered of {len(CASES)}",
                f"latency p50 {ms[len(ms) // 2]:.0f} ms, p95 {ms[int(len(ms) * 0.95)]:.0f} ms",
                *(f"miss       {m}" for m in misses),
                *(f"unanswered {u}" for u in unanswered),
            ]
        )
        print("\n" + report)
        assert answered >= 0.9 * len(CASES), report
        assert accuracy >= TARGET, report
