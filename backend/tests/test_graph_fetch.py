"""Nodes 3-5 honour the plan.

All four fetch nodes are wired to fan out from the planner, so every one of
them is scheduled on every run. Routing only means something if a node the
plan left out then does nothing — otherwise a go/no-go question pays for an
SST and chlorophyll fetch nobody asked for, and the trace shows it.

conditions_at is the network boundary; it is replaced with a recorder.
"""

import pytest

from dhruva.graph import build
from dhruva.graph.state import Intent, initial_state
from dhruva.sources.registry import Variable


@pytest.fixture
def fetched(monkeypatch):
    calls: list[tuple[Variable, ...]] = []

    class _Result:
        primary: dict = {}  # noqa: RUF012
        errors: list = []  # noqa: RUF012

    async def recorder(lat, lon, when, *, registry, adapters, variables):
        calls.append(tuple(variables))
        return _Result()

    monkeypatch.setattr(build, "conditions_at", recorder)
    return calls


def _state(nodes: list[str], variables: list[Variable]):
    state = initial_state("q", 11.05, 79.95)
    state["plan"] = {"intent": Intent.GO_NO_GO, "nodes": nodes, "variables": variables}
    return state


GO_NO_GO_VARS = [Variable.WAVE_HEIGHT, Variable.WIND_SPEED, Variable.WIND_DIRECTION]


async def test_a_node_the_plan_left_out_fetches_nothing(fetched):
    out = await build.ocean(_state(["discovery", "weather", "geo"], GO_NO_GO_VARS))

    assert out == {}
    assert fetched == []


async def test_a_planned_node_fetches_only_the_planned_variables(fetched):
    await build.weather(_state(["discovery", "weather", "geo"], GO_NO_GO_VARS))

    assert fetched == [(Variable.WAVE_HEIGHT, Variable.WIND_SPEED, Variable.WIND_DIRECTION)]


async def test_geo_left_out_of_the_plan_does_not_touch_the_database(monkeypatch):
    monkeypatch.setattr(build, "database_dsn", lambda: pytest.fail("geo ran unplanned"))

    out = await build.geo(_state(["discovery", "ocean"], [Variable.SST]))

    assert out == {}


async def test_without_a_plan_a_node_still_fetches_what_it_serves(fetched):
    """Studio and scripts can run a node on a bare state; that must not go dark."""
    state = initial_state("q", 11.05, 79.95)

    await build.ocean(state)

    assert len(fetched) == 1
    assert set(fetched[0]) == {
        Variable.SST,
        Variable.CHLOROPHYLL,
        Variable.CURRENT_SPEED,
        Variable.CURRENT_DIRECTION,
    }
