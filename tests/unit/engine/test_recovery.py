"""Rebuilding a run from its events."""

import pytest

from swarmax.engine.checkpoint import Checkpoint
from swarmax.engine.recovery import recover
from swarmax.errors import RunError
from tests.fixtures.runs import call, run, says, uses


async def test_events_alone_equal_the_final_checkpoint():
    """A run's snapshot and a rebuild from its log are the same state."""
    result, engine, events = await run(
        [uses(call("lookup", key="a"), call("add", "c2", left=1, right=2)), says("end")]
    )
    saved = Checkpoint.load(engine.store.load_checkpoint(result.run_id))
    assert recover(events) == saved
    assert saved.status == "done" and saved.answer == "end"


async def test_tool_results_join_in_call_order():
    """Whatever finishes first, the history has the order of the calls."""
    _, _, events = await run(
        [uses(call("add", "first", left=1, right=1), call("lookup", "second", key="a")), says()]
    )
    state = recover(events)
    assert [m.tool_call_id for m in state.messages if m.role == "tool"] == ["first", "second"]


async def test_usage_is_rebuilt():
    """Usage comes from the completions in the log."""
    result, _, events = await run([uses(call("lookup", key="a")), says()])
    assert recover(events).usage == result.usage


def test_a_log_without_the_run_raises():
    """There is nothing to rebuild."""
    with pytest.raises(RunError, match="run.started"):
        recover([])
