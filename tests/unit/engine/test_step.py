"""One step: tool order, concurrency, retries and answers."""

import asyncio

import pydantic

from geomind.agents import Agent, Output
from geomind.prompts import Prompt
from geomind.tools import finish, tool
from geomind.types import Action, ToolCall
from tests.fixtures.runs import (
    EXECUTED,
    call,
    lookup,
    of_type,
    run,
    save_note,
    says,
    uses,
)


class Rendezvous:
    """Let two calls continue only when both have started."""

    def __init__(self):
        """Prepare the barrier."""
        self.arrived = 0
        self.both = asyncio.Event()

    async def meet(self):
        """Wait for the other call, with a limit so a sequential run fails instead of hanging."""
        self.arrived += 1
        if self.arrived == 2:
            self.both.set()
        await asyncio.wait_for(self.both.wait(), 0.2)
        return "met"


MEETING = Rendezvous()


@tool(effect="read")
async def meet():
    """Meet the other call."""
    return await MEETING.meet()


class Meeters(Agent):
    """Has one concurrent tool."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Tools
        self.meet = meet


class Typed(pydantic.BaseModel):
    """A typed answer."""

    value: int


class Reporter(Agent):
    """Answers in a fixed shape."""

    def __init__(self):
        """Declare the output."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Report.")

        # Tools
        self.finish = finish

        # Output
        self.output = Output(Typed, max_retries=1)


class Rule(Agent):
    """Decides without a model."""

    async def forward(self, context):
        """Answer at once."""
        return Action(text="by rule")


async def test_read_and_compute_tools_run_concurrently():
    """Two read calls meet, which only works if they overlap."""
    MEETING.__init__()
    result, _, events = await run([uses(call("meet", "a"), call("meet", "b")), says()], Meeters())
    assert result.status == "done"
    calls = [event for event in of_type(events, "tool.result") if event.call_id]
    assert [event.output for event in calls] == ["met", "met"]


async def test_other_tools_run_in_order():
    """A write tool makes the whole step sequential."""
    _, _, events = await run(
        [
            uses(
                call("save_note", "a", text="x"),
                call("lookup", "b", key="k"),
                call("save_again", "c", text="y"),
            ),
            says(),
        ]
    )
    assert EXECUTED == ["save_note", "lookup", "save_again"]
    assert [event.call_id for event in of_type(events, "tool.started")] == ["a", "b", "c"]


async def test_step_events_in_order():
    """One step has one fixed order of public events."""
    _, _, events = await run([uses(call("lookup", key="k")), says()])
    public = [event.type for event in events if event.is_public]
    assert public == [
        "run.started",
        "step.started",
        "tool.started",
        "tool.finished",
        "step.finished",
        "usage",
        "step.started",
        "step.finished",
        "usage",
        "run.finished",
    ]


async def test_unknown_tool_is_a_result_for_the_model():
    """A tool that does not exist gets a close match back."""
    _, _, events = await run([uses(call("lookupp", key="k")), says()])
    output = of_type(events, "tool.result")[0].output
    assert "did you mean 'lookup'" in output["error"]["message"]


async def test_a_tool_at_its_retry_limit_is_refused_and_a_call_after_that_stops_the_run():
    """QA-269: two invalid calls ended a run with no answer; the tool is refused instead."""
    bad = [uses(call("add", name, left=name, right=1)) for name in ("a", "b", "c", "d")]
    result, _, events = await run(bad)
    refused = [event for event in of_type(events, "tool.result") if event.source == "blocked"]
    assert [event.call_id for event in refused] == ["c"]
    assert "refused for the rest of this run" in refused[0].output["error"]["message"]
    assert (result.stop_reason, result.status) == ("error", "failed")
    assert "called again after it was refused" in result.message


async def test_a_refused_tool_leaves_the_agent_free_to_answer():
    """After the refusal the agent finishes with what it has: the run is done, not failed."""
    bad = [uses(call("add", name, left=name, right=1)) for name in ("a", "b", "c")]
    result, _, _ = await run([*bad, says("answer from what I read")])
    assert (result.status, result.answer) == ("done", "answer from what I read")


async def test_an_unknown_tool_at_its_limit_is_refused_before_the_run_stops():
    """The same for a tool that does not exist (``MAX_UNKNOWN_CALLS``)."""
    steps = [uses(call("lookupp", name, key=name)) for name in ("a", "b", "c")] + [says("done")]
    result, _, events = await run(steps)
    sources = {event.call_id: event.source for event in of_type(events, "tool.result")}
    assert sources["c"] == "blocked" and sources["b"] == "tool"
    assert result.status == "done"


async def test_parallel_failing_calls_of_one_step_do_not_stop_the_run():
    """The run: three failing calls in one step ended it before the model saw an error."""
    result, _, _ = await run(
        [
            uses(
                call("add", "a", left="x", right=1),
                call("add", "b", left="y", right=1),
                call("add", "c", left="x", right=1),
            ),
            says(),
        ]
    )
    assert result.stop_reason == "answer"


async def test_a_valid_call_resets_the_count():
    """Only failures in a row count."""
    result, _, _ = await run(
        [
            uses(call("add", "a", left="x", right=1)),
            uses(call("add", "b", left=1, right=1)),
            uses(call("add", "c", left="x", right=1)),
            says(),
        ]
    )
    assert result.stop_reason == "answer"


async def test_finish_ends_the_run_after_the_other_calls():
    """The answer of ``finish`` wins after the step's calls ran."""
    result, _, _ = await run(
        [uses(call("lookup", "a", key="k"), call("finish", "b", answer="final"))]
    )
    assert (result.stop_reason, result.answer) == ("finish", "final")
    assert EXECUTED == ["lookup"]


async def test_typed_answer_is_validated():
    """A valid answer through ``finish`` is parsed."""
    result, _, _ = await run([uses(call("finish", answer={"value": 3}))], Reporter())
    assert result.answer == {"value": 3}


async def test_failed_output_goes_back_to_the_model():
    """The model gets the error, and its next answer counts."""
    result, _, events = await run([says("no json"), says('{"value": 1}')], Reporter())
    assert result.answer == {"value": 1}
    feedback = of_type(events, "tool.result")[0]
    assert feedback.feedback == "output" and feedback.call_id is None


async def test_output_retries_are_limited():
    """Past ``max_retries`` the run fails."""
    result, _, _ = await run([says("a"), says("b"), says("c")], Reporter())
    assert (result.stop_reason, result.status) == ("error", "failed")


async def test_rule_based_step_is_logged_as_a_completion():
    """A step without a model still leaves its action in the log."""
    result, engine, events = await run([], Rule())
    assert result.answer == "by rule"
    assert of_type(events, "llm.completed")[0].completion.model == "rule"
    assert engine.llm.llm.calls == []


RANGES = {
    "size.doublets": {"min": 1, "max": 3},
    "d0.nominal_flow": {
        "min": {"value": 50, "unit": "m3/h"},
        "max": {"value": 300, "unit": "m3/h"},
    },
    "heat_pump.capacity": {"min": {"value": 0, "unit": "MW"}, "max": {"value": 30, "unit": "MW"}},
}
"""Part of the ``set_ranges`` input design_lead dfa8eb2f sent 37 times (run 4ca94d6e)."""

SET_CALLS = []


@tool(effect="write", sets_input=True)
def set_ranges(design: str, ranges: dict, name: str):
    """Set ranges: a write whose result follows from its input alone."""
    SET_CALLS.append(name)
    return {"design": f"design/{name}", "ranges": ranges}


class Ranger(Agent):
    """Sets ranges and reads."""

    def __init__(self):
        """Declare the tools."""
        super().__init__()

        # Tools
        self.set_ranges = set_ranges
        self.lookup = lookup
        self.save_note = save_note


def _ranges_call(call_id):
    """Return the recorded ``set_ranges`` call."""
    tool_input = {"design": "design/backup_peak", "ranges": RANGES, "name": "ranges_2027"}
    return ToolCall(id=call_id, name="set_ranges", input=tool_input)


async def test_a_repeated_successful_read_is_answered_from_the_first():
    """The same read again, with nothing written between, does not run and names step 1."""
    result, _, events = await run(
        [uses(call("lookup", "a", key="k")), uses(call("lookup", "b", key="k")), says()]
    )
    assert result.stop_reason == "answer" and EXECUTED == ["lookup"]
    second = of_type(events, "tool.result")[1]
    assert second.source == "repeat" and 'same result as step 1: "value of k"' in second.output


async def test_a_write_between_makes_the_same_read_run_again():
    """A read after a write may read something else, so it runs."""
    await run(
        [
            uses(call("lookup", "a", key="k")),
            uses(call("save_note", "b", text="x")),
            uses(call("lookup", "c", key="k")),
            says(),
        ]
    )
    assert EXECUTED == ["lookup", "save_note", "lookup"]


async def test_a_write_without_sets_input_runs_every_time():
    """``save_again`` is a write that does not set its input: the guard leaves it out."""
    await run(
        [uses(call("save_again", "a", text="y")), uses(call("save_again", "b", text="y")), says()]
    )
    assert EXECUTED == ["save_again", "save_again"]


async def test_the_same_set_ranges_runs_once_and_its_repeats_end_the_run():
    """The run: one set_ranges call 37 times; it runs once and three repeats end the run."""
    SET_CALLS.clear()
    result, _, events = await run([uses(_ranges_call(f"c{index}")) for index in range(6)], Ranger())
    assert SET_CALLS == ["ranges_2027"]
    assert result.stop_reason == "error" and "same call as an earlier successful one" in (
        result.message
    )
    notes = [event for event in of_type(events, "tool.result") if event.source == "repeat"]
    assert len(notes) == 3 and "same result as step 1" in notes[0].output


def test_the_same_error_twice_in_a_row_says_to_change_the_call():
    """IMP-015: one code on one path twice for a tool: the second result says so."""
    from types import SimpleNamespace

    from geomind.engine.step import with_repeat_note
    from geomind.types.messages import ToolResult

    session = SimpleNamespace()
    error = {"error": {"code": "invalid_input", "path": "inlets", "message": "m"}}
    first = ToolResult(call_id="a", tool="evaluate_module", output=error, is_error=True)
    second = ToolResult(call_id="b", tool="evaluate_module", output=dict(error), is_error=True)
    assert "repeated" not in with_repeat_note(session, first).output
    assert "second time" in with_repeat_note(session, second).output["repeated"]


FAILS = []


@tool(effect="compute")
async def picky(value: int):
    """Refuse every value but 1."""
    from geomind.errors import ToolError

    FAILS.append(value)
    if value != 1:
        raise ToolError(f"picky: value = {value}; expected 1", path="value")
    return "ok"


class Picky(Agent):
    """Has one tool that refuses."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Tools
        self.picky = picky


async def test_a_call_identical_to_a_failed_one_is_not_run_again():
    """QA-143: the same refused call is answered from its first refusal, not run again."""
    FAILS.clear()
    script = [
        uses(call("picky", "a", value=2)),
        uses(call("picky", "b", value=2)),
        uses(call("picky", "c", value=1)),
        says(),
    ]
    result, _, events = await run(script, Picky())
    assert result.status == "done" and FAILS == [2, 1]
    second = next(e for e in of_type(events, "tool.result") if e.call_id == "b")
    assert second.output["error"]["code"] == "failed_before"


@tool(effect="write")
async def refused_write(text: str):
    """Write a note; its precheck always refuses."""
    return f"wrote {text}"


async def _always_refused(context, **arguments):
    """Refuse every call, as set_case's dry run refused the same case (QA-301)."""
    from geomind.errors import ToolError

    raise ToolError("refused_write: file 'x.csv' not found", code="missing_value")


refused_write.precheck = _always_refused


class Refused(Agent):
    """Has one write tool its precheck refuses."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Write.")

        # Tools
        self.refused_write = refused_write
        self.finish = finish


async def test_the_same_call_refused_before_its_card_stops_the_run():
    """QA-301: twelve identical set_case calls refused by the precheck never stopped the run."""
    from geomind.engine.permissions import Permissions
    from tests.fixtures.runs import Model

    agent = Refused()
    agent.model = Model("fake/model")
    steps = [uses(call("refused_write", f"c{n}", text="a")) for n in range(6)] + [says()]
    result, _, events = await run(steps, agent=agent, permissions=Permissions(mode="ask"))
    assert (result.status, result.stop_reason) == ("failed", "error")
    assert "failed 3 times in a row" in result.message
    assert len(of_type(events, "tool.result")) == 3


@tool(effect="write")
async def note_then_fail(context, text: str):
    """Change the problem state, then fail, as a nested run that failed after its set_case."""
    from geomind.errors import ToolError

    await context.session.change_state([{"op": "replace", "path": "/goal", "value": text}])
    raise ToolError("note_then_fail: failed after writing", code="internal")


class Noter(Agent):
    """Reads, and writes the state with a call that fails."""

    def __init__(self):
        """Declare the tools."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Work.")

        # Tools
        self.lookup = lookup
        self.note_then_fail = note_then_fail
        self.finish = finish


async def test_a_read_after_a_failed_call_that_changed_the_state_runs_again():
    """QA-319: a nested run failed after its write; the same read was answered from before it."""
    from geomind.agents import Model

    agent = Noter()
    agent.model = Model("fake/model")
    await run(
        [
            uses(call("lookup", "a", key="k")),
            uses(call("note_then_fail", "b", text="x")),
            uses(call("lookup", "c", key="k")),
            says(),
        ],
        agent=agent,
    )
    assert EXECUTED == ["lookup", "lookup"]


class Stater(Agent):
    """The worker's tools and ``update_state``, which changes the problem state."""

    def __init__(self):
        """Declare the tools."""
        from geomind.tools import update_state
        from tests.fixtures.runs import Model, Worker

        super().__init__()
        self.prompt = Prompt.text("Work.")
        for name, item in Worker().tools().items():
            setattr(self, name, item)
        self.update_state = update_state
        self.model = Model("fake/model")


async def test_a_refused_tool_runs_again_once_the_problem_state_changed():
    """QA-331: read_case refused for no case stayed refused after the case was saved."""
    bad = [uses(call("add", name, left=name, right=1)) for name in ("a", "b", "c")]
    change = {"op": "add", "path": "/goal", "value": "a new goal"}
    steps = [
        *bad,
        uses(call("update_state", "s", changes=[change])),
        uses(call("add", "d", left=1, right=2)),
        says("done"),
    ]
    result, _, events = await run(steps, agent=Stater())
    sources = {event.call_id: event.source for event in of_type(events, "tool.result")}
    assert sources["c"] == "blocked" and sources["d"] == "tool"
    assert result.status == "done"
