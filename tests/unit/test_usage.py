"""``RunResult.usage`` counts every nested run: the routing call, delegates and loops."""

import json

import pytest

import geomind as gd
from geomind import runtime
from geomind.cli import _models, render_markdown
from geomind.engine import Context, Engine, Permissions
from geomind.providers import FakeLLM
from geomind.stores import MemoryRunStore
from geomind.types import Usage
from geomind.types.runlog import runlog
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
    text = json.dumps({"kind": "loop", "loop": loop, "agent": "analyst", **fields})
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
    from geomind.agents import Designer, Verifier
    from geomind.loops import MakerCheckerLoop

    monkeypatch.setattr("geomind.run.loop_of", lambda _: MakerCheckerLoop(Designer(), Verifier()))
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([route("design")]), store=store).start()
    events = store.load_events(result.run_id)
    assert result.stop_reason == "not_implemented"
    assert same_usage(result.usage, logged(events)) and same_usage(result.usage, ROUTING)
    sequences = [event.sequence for event in events]
    assert sequences == sorted(set(sequences))


def test_the_export_totals_equal_the_usage():
    """``show --format md`` totals, by agent and by step, are ``RunResult.usage``."""
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([route(), says("answer")]), store=store).start()
    text = render_markdown(runlog(store.load_events(result.run_id)))
    usage = result.usage
    counts = f"| 2 | {usage.input_tokens} | {usage.output_tokens} | {round(usage.cost, 6)} |"
    assert f"| Total {counts}" in text
    assert f"| Total | | | | {counts}" in text
    assert f"| coordinator | 1 | {ROUTING.input_tokens} |" in text


def test_the_manifest_names_the_routing_model():
    """The models per agent include the coordinator's."""
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([route(), says("answer")]), store=store).start()
    models = _models(store.load_events(result.run_id))
    assert set(models) == {"coordinator", "analyst"}
