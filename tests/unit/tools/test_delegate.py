"""The tool that runs a nested agent."""

import pytest

from swarmax import runtime
from swarmax.tools import Delegate, dispatch
from swarmax.types import Request, RunResult, ToolCall
from tests.fixtures.sessions import StubSession


class Helper:
    """Helps with a task.

    More detail.
    """

    name = "helper"


def call(task="do it"):
    """Return one call."""
    return ToolCall(id="c1", name="helper", input={"task": task})


def test_tool_describes_the_agent():
    """The model sees the agent's name and first paragraph."""
    schema = Delegate(Helper()).schema()
    assert (schema["name"], schema["description"]) == ("helper", "Helps with a task.")
    assert schema["input_schema"]["required"] == ["task"]


def test_a_nested_run_is_not_pure_and_not_idempotent():
    """It never runs beside others, again in a replay or again after a crash."""
    delegate = Delegate(Helper())
    assert not delegate.is_pure and not delegate.idempotent


async def test_answer_is_cut_to_the_token_limit():
    """The parent sees only a short summary."""
    session = StubSession()
    session.result = RunResult(run_id="c", status="done", answer="x" * 1000)
    with runtime.activate(session):
        result = await dispatch(Delegate(Helper(), max_summary_tokens=10), call())
    assert result.output == "x" * 40
    assert session.delegated[1] == "do it"


async def test_waiting_nested_run_pauses_the_parent():
    """The request of the nested run passes through."""
    session = StubSession()
    request = Request(id="q", kind="approval", message="ok?")
    session.result = RunResult(run_id="c", status="waiting", request=request)
    with runtime.activate(session):
        assert await dispatch(Delegate(Helper()), call()) == request


async def test_failed_nested_run_is_an_error_result():
    """The model reads that the delegate failed and why."""
    session = StubSession()
    session.result = RunResult(run_id="c", status="failed", stop_reason="step_limit")
    with runtime.activate(session):
        result = await dispatch(Delegate(Helper()), call())
    assert result.is_error and "step_limit" in result.output["error"]["message"]


@pytest.mark.parametrize("tokens", [None])
async def test_default_limit_comes_from_the_runtime(tokens):
    """The runtime holds the default summary size."""
    session = StubSession()
    session.result = RunResult(run_id="c", status="done", answer="x" * 1000)
    with runtime.activate(session), runtime.settings(delegate_summary_tokens=1):
        result = await dispatch(Delegate(Helper(), tokens), call())
    assert result.output == "xxxx"
