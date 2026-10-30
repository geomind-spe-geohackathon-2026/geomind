"""Rebuilding a run from its events."""

import dataclasses

import pytest

from geomind.engine import Permissions
from geomind.engine.hooks import Hook
from geomind.engine.recovery import agent_class, recover
from geomind.engine.state import RunState
from geomind.errors import RunError
from tests.fixtures.runs import call, run, says, uses


class Watcher(Hook):
    """Keep hold of the live state of a run."""

    def before_llm_call(self, context, agent, messages):
        """Remember the session."""
        self.state = context.session.state


def without_sequence(state):
    """Return a state without the number only ``recover`` fills in."""
    return dataclasses.replace(state, sequence=0)


async def test_events_alone_equal_the_live_state_at_the_end():
    """A rebuild from the log is the state the run had."""
    watcher = Watcher()
    _, _, events = await run(
        [uses(call("lookup", key="a"), call("add", "c2", left=1, right=2)), says("end")],
        hooks=[watcher],
    )
    rebuilt = recover(events)
    assert without_sequence(rebuilt) == watcher.state
    assert (rebuilt.status, rebuilt.answer) == ("done", "end")


async def test_events_alone_equal_the_live_state_at_a_pause():
    """The same holds for a run that waits."""
    watcher = Watcher()
    _, _, events = await run(
        [uses(call("save_note", text="x"))], hooks=[watcher], permissions=Permissions()
    )
    assert without_sequence(recover(events)) == watcher.state


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


def test_a_class_that_does_not_import_raises():
    """A run naming a class that is gone is a run error."""
    with pytest.raises(RunError, match="importable"):
        agent_class(RunState(agent_class="no.such.module:X"))
