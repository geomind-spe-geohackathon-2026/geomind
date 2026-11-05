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


def _failed(state, calls, step, output):
    """Apply one step whose ``calls`` all failed with ``output``, as recovery does."""
    from geomind.engine.recovery import _count_failure
    from geomind.types.events import ToolRecorded

    state.step, state.calls = step, calls
    for made in calls:
        event = ToolRecorded(
            run_id="r",
            sequence=step,
            time="t",
            agent="a",
            index=step,
            call_id=made.id,
            tool=made.name,
            output=output,
            is_error=True,
            is_validation=True,
        )
        _count_failure(state, event)


UNKNOWN = {
    "error": {
        "path": "with_schema",
        "code": "invalid_input",
        "message": "read_plant: unknown argument(s) with_schema",
    }
}
"""The error each of the design lead's three ``read_plant`` calls got in the run."""


PLANT_CLASSES = ("HeatingCoolingPlant", "ATESPlant", "HeatingFullCoolingPlant")
"""The classes of the design lead's three parallel ``read_plant`` calls in the run."""


def test_calls_of_one_step_with_one_error_are_not_a_repeat():
    """The run: three ``read_plant`` of other plant classes in one step ended the design lead."""
    from geomind.engine.state import RunState
    from geomind.types import ToolCall

    state = RunState()
    calls = [
        ToolCall(
            id=f"c{index}",
            name="read_plant",
            input={"plant_class": name, "with_schema": "true"},
        )
        for index, name in enumerate(PLANT_CLASSES)
    ]
    _failed(state, calls, 1, UNKNOWN)
    assert state.repeated == 1 and state.failures["read_plant"] == 1


def test_the_same_call_counts_again_only_once_the_model_saw_its_error():
    """One input sent three times in one step is one; sent again in later steps it adds up."""
    from geomind.engine.state import RunState
    from geomind.types import ToolCall

    state = RunState()
    same = {"plant_class": "ATESPlant", "with_schema": "true"}
    calls = [ToolCall(id=f"c{index}", name="read_plant", input=same) for index in range(3)]
    _failed(state, calls, 1, UNKNOWN)
    assert state.repeated == 1
    for step in (2, 3):
        _failed(state, [ToolCall(id=f"s{step}", name="read_plant", input=same)], step, UNKNOWN)
    assert state.repeated == 3 and state.failures["read_plant"] == 3


def test_another_input_with_the_same_error_starts_the_count_again():
    """Same tool, same error, another argument: the call is not the same, so the count is 1."""
    from geomind.engine.state import RunState
    from geomind.types import ToolCall

    state = RunState()
    for step, name in enumerate(("lcoh", "lcoc", "lcts"), start=1):
        call = ToolCall(id=f"c{step}", name="read_result", input={"reference": "x", "path": name})
        _failed(state, [call], step, UNKNOWN)
    assert state.repeated == 1


async def test_the_sequence_goes_on_from_the_highest_event_in_any_order():
    """QA-336: a resume went on below the stream's end; the highest sequence counts, not the last."""
    _, _, events = await run([uses(call("lookup", "c1", key="k")), says("done")])
    highest = max(event.sequence for event in events)
    shuffled = [*events[-2:], *events[:-2]]
    assert recover(shuffled).sequence == highest
