"""``RunResult.usage`` counts every nested run: the routing call, delegates and loops."""

import json

import pytest

import geomind as gd
from geomind import runtime
from geomind.engine import Context, Engine, Permissions
from geomind.export import models_by_agent, render_export
from geomind.providers import FakeLLM
from geomind.stores import MemoryRunStore
from geomind.types import Usage
from tests.fixtures.runs import Lead, Worker, call, context, logged, same_usage, says, uses

ROUTING = Usage(input_tokens=1000, output_tokens=20, cost=0.25)
"""The usage of the coordinator's call, unlike any other, so a missing route shows."""


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Retry without sleeping."""
    with runtime.settings(retry_delay=0):
        yield


def route(loop="tool", **fields):
    """Return the coordinator's completion with the routing usage."""
    text = json.dumps({"kind": "loop", "loop": loop, "agent": "analysis_lead", **fields})
    return says(text, usage=ROUTING)


def test_the_routing_call_counts():
    """The coordinator's tokens are part of the run's usage."""
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([route(), says("answer")]), store=store).start()
    events = store.load_events(result.run_id)
    assert same_usage(result.usage, logged(events))
    assert result.usage.input_tokens == ROUTING.input_tokens + 10


def test_the_routing_call_counts_after_a_resume_in_a_fresh_process(tmp_path):
    """A run rebuilt from its files keeps the coordinator's tokens."""
    script = [uses(call("ask_user", question="which?")), says("end")]
    run = gd.Run(
        message="hello", llm=FakeLLM([route(), *script]), store=gd.stores.FileRunStore(tmp_path)
    )
    paused = run.start()
    store = gd.stores.FileRunStore(tmp_path)
    fresh = gd.Run.load(run.id, llm=FakeLLM(script[1:]), store=store)
    result = fresh.resume(paused.request.id, {"text": "this"})
    assert same_usage(result.usage, logged(store.load_events(run.id)))
    assert result.usage.input_tokens == ROUTING.input_tokens + 20


async def test_a_routing_run_and_a_delegate_both_count():
    """A run routed first that delegates adds both nested runs to its usage."""
    engine = Engine(
        llm=FakeLLM(
            [
                says("route", usage=ROUTING),
                uses(call("helper", task="t")),
                says("found"),
                says("end"),
            ]
        ),
        permissions=Permissions(mode="auto"),
    )
    start = context()
    routing = Context(f"{start.run_id}-route", start.messages)
    await engine.run_first(Worker(), routing, root=start.run_id)
    result = await engine.run(Lead(), start)
    assert same_usage(result.usage, logged(engine.store.load_events(start.run_id)))
    assert result.usage.input_tokens == ROUTING.input_tokens + 30


def test_a_routed_loop_that_is_not_built_counts_its_route(monkeypatch):
    """A declined run still spent the coordinator's tokens, and continues its log's numbering."""
    from geomind.errors import NotImplementedYet
    from geomind.loops import Loop

    class Unbuilt(Loop):
        """A loop that is not built yet."""

        name = "unbuilt"
        agent = Worker()

        async def run(self, engine, task):
            """Say so."""
            raise NotImplementedYet("Unbuilt comes later")

    monkeypatch.setattr("geomind.run.loop_of", lambda _: Unbuilt())
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([route("design")]), store=store).start()
    events = store.load_events(result.run_id)
    assert result.stop_reason == "not_implemented"
    assert same_usage(result.usage, logged(events)) and same_usage(result.usage, ROUTING)
    sequences = [event.sequence for event in events]
    assert sequences == sorted(set(sequences))


def test_the_export_totals_equal_the_usage():
    """``show --format md`` totals, by agent, session and step, are ``RunResult.usage``."""
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([route(), says("answer")]), store=store).start()
    text = render_export(store.load_events(result.run_id))
    usage = result.usage
    counts = f"| 2 | {usage.input_tokens} | 0 | {usage.output_tokens} | {round(usage.cost, 6)} |"
    assert text.count(f"| Total {counts}") == 3
    assert (result.total.input_tokens, result.total.output_tokens) == (
        usage.input_tokens,
        usage.output_tokens,
    )
    assert [s.agent for s in result.sessions] == ["coordinator", "analysis_lead"]
    assert f"| coordinator | 1 | {ROUTING.input_tokens} |" in text


def test_the_manifest_names_the_routing_model():
    """The models per agent include the coordinator's."""
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([route(), says("answer")]), store=store).start()
    models = models_by_agent(store.load_events(result.run_id))
    assert set(models) == {"coordinator", "analysis_lead"}
