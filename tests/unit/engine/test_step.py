"""One step: tool order, concurrency, retries and answers."""

import asyncio

import pydantic

from geomind.agents import Agent, Output
from geomind.prompts import Prompt
from geomind.tools import finish, tool
from geomind.types import Action
from tests.fixtures.runs import (
    EXECUTED,
    call,
    of_type,
    run,
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


async def test_validation_failures_in_a_row_stop_the_run():
    """After ``max_retries`` invalid calls of one tool the run stops."""
    result, _, _ = await run(
        [uses(call("add", "a", left="x", right=1)), uses(call("add", "b", left="y", right=1))]
    )
    assert (result.stop_reason, result.status) == ("error", "failed")


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
