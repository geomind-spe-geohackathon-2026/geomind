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


def test_a_result_stored_whole_keeps_its_short_form_and_an_old_one_does_not():
    """The state remembers the short form of a result with a reference; a 0.4.x offload has it."""
    from geomind.engine.recovery import _remember_stored
    from geomind.engine.state import RunState
    from geomind.types.events import ToolRecorded

    state = RunState()
    whole = ToolRecorded(
        run_id="r", index=0, call_id="a", output={"k": "v" * 3000}, reference="result-1"
    )
    old = ToolRecorded(
        run_id="r",
        index=1,
        call_id="b",
        output={"reference": "result-2", "summary": "s"},
        reference="result-2",
    )
    plain = ToolRecorded(run_id="r", index=2, call_id="c", output={"k": 1})
    for event in (whole, old, plain):
        _remember_stored(state, event)
    assert list(state.stored) == ["a"] and "result-1" in state.stored["a"]


def test_a_log_naming_a_renamed_agent_finds_its_new_class():
    """A log of 0.4.22.dev23 names ``geomind.agents.design.designer:Designer``: it is DesignLead."""
    from geomind.agents import DesignLead
    from geomind.engine.recovery import agent_class
    from geomind.engine.state import RunState

    state = RunState(agent_class="geomind.agents.design.designer:Designer")
    assert agent_class(state) is DesignLead


def test_every_renamed_class_path_imports():
    """Each new path of ``RENAMED_CLASSES`` names a class that exists."""
    from geomind.engine.recovery import RENAMED_CLASSES
    from geomind.utils.imports import import_class

    assert all(isinstance(import_class(path), type) for path in RENAMED_CLASSES.values())


def test_the_same_bad_value_beside_other_input_is_the_same_failure():
    """#49: a made-up reference sent six times, each with another ``path``, counts as repeated."""
    from geomind.engine.recovery import _count_repeat
    from geomind.engine.state import RunState
    from geomind.types import ToolCall
    from geomind.types.events import ToolRecorded

    state = RunState()
    error = {"error": {"path": "reference", "code": "unknown_name", "message": "no such result"}}
    for index, path in enumerate(("lcoh", "lcoc", "lcts")):
        call = ToolCall(
            id=f"c{index}", name="read_result", input={"reference": "result/x", "path": path}
        )
        state.calls = [call]
        event = ToolRecorded(
            run_id="r",
            sequence=index,
            time="t",
            agent="a",
            index=1,
            call_id=call.id,
            tool="read_result",
            output=error,
            is_error=True,
        )
        _count_repeat(state, event)
    assert state.repeated == 3
