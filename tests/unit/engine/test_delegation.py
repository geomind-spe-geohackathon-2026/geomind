"""The small parts of delegation; ``tests/integration/test_delegate.py`` runs the whole."""

from geomind.engine import Engine, Permissions
from geomind.engine.delegation import run_child
from geomind.engine.hooks import TokenBudget
from geomind.providers import FakeLLM
from geomind.types import Usage
from tests.fixtures.runs import Helper, Lead, call, context, of_type, run, says, uses


async def test_run_child_shares_the_log_of_its_parent():
    """A delegate call goes through ``run_child`` and lands in the root's log."""
    engine = Engine(
        llm=FakeLLM([uses(call("helper", task="t")), says("found"), says("end")]),
        permissions=Permissions(mode="auto"),
    )
    start = context()
    await engine.run(Lead(), start)
    started = of_type(engine.store.load_events(start.run_id), "run.started")
    assert [event.parent for event in started] == [None, start.run_id]
    assert isinstance(Lead().helper_agent, Helper) and callable(run_child)


async def test_a_nested_run_that_a_budget_stopped_fails_with_the_budget_code():
    """The parent reads code budget and which budget, spent and cap, not an internal error."""
    script = [
        uses(call("helper", task="t"), usage=Usage(input_tokens=900)),
        uses(call("lookup", key="k")),
        says("found"),
        says("end"),
    ]
    _, _, events = await run(script, agent=Lead(), hooks=[TokenBudget(910)])
    recorded = next(e for e in events if e.type == "tool.result" and e.tool == "helper")
    assert recorded.is_error and recorded.output["error"]["code"] == "budget"
    assert "helper: run token budget: used" in recorded.output["error"]["message"]
    assert "of 910" in recorded.output["error"]["message"]
