"""The tool that runs a nested agent."""

import pytest

from geomind import runtime
from geomind.engine import Context
from geomind.tools import Delegate, dispatch
from geomind.types import Request, RunResult, ToolCall
from tests.fixtures.runs import Worker
from tests.fixtures.runs import call as fixture_call
from tests.fixtures.runs import context, engine_for, stopped_at_limit, uses
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
    result = await dispatch(
        Delegate(Helper(), max_summary_tokens=10), call(), Context(session=session)
    )
    assert result.output == "x" * 40
    assert session.delegated[1] == "do it"


async def test_a_typed_answer_comes_back_as_json():
    """A typed answer is JSON text the parent can parse, not Python's repr of a dict."""
    import json

    session = StubSession()
    session.result = RunResult(run_id="c", status="done", answer={"values": [1], "ok": True})
    result = await dispatch(Delegate(Helper()), call(), Context(session=session))
    assert json.loads(result.output) == {"values": [1], "ok": True}


async def test_waiting_nested_run_pauses_the_parent():
    """The request of the nested run passes through."""
    session = StubSession()
    request = Request(id="q", kind="approval", message="ok?")
    session.result = RunResult(run_id="c", status="waiting", request=request)
    assert await dispatch(Delegate(Helper()), call(), Context(session=session)) == request


async def test_failed_nested_run_is_an_error_result():
    """The model reads that the delegate failed and why."""
    session = StubSession()
    session.result = RunResult(run_id="c", status="failed", stop_reason="step_limit")
    result = await dispatch(Delegate(Helper()), call(), Context(session=session))
    assert result.is_error and "step_limit" in result.output["error"]["message"]


@pytest.mark.parametrize("tokens", [None])
async def test_default_limit_comes_from_the_runtime(tokens):
    """The runtime holds the default summary size."""
    session = StubSession()
    session.result = RunResult(run_id="c", status="done", answer="x" * 1000)
    with runtime.settings(delegate_summary_tokens=1):
        result = await dispatch(Delegate(Helper(), tokens), call(), Context(session=session))
    assert result.output == "xxxx"


async def test_a_nested_run_that_stopped_says_why():
    """A limit or a refusal inside the nested run reaches the model with its message."""
    session = StubSession()
    session.result = RunResult(
        run_id="c", status="failed", stop_reason="step_limit", message="stopped after 30 steps"
    )
    error = (await dispatch(Delegate(Helper()), call(), Context(session=session))).output["error"]
    assert error["code"] == "nested_stopped"
    assert "stopped after 30 steps" in error["message"]


async def test_a_nested_run_that_crashed_keeps_the_detail_in_the_log():
    """A crash is ``internal``: its text is a bug's, so the model reads only that it happened."""
    session = StubSession()
    session.result = RunResult(run_id="c", status="failed", stop_reason="error")
    error = (await dispatch(Delegate(Helper()), call(), Context(session=session))).output["error"]
    assert error["code"] == "internal" and "log" in error["message"]


async def test_a_crash_leaves_no_message_on_the_result():
    """The engine keeps a crash's text in the log and off the ``RunResult``."""
    engine = engine_for([RuntimeError("secret detail")])
    result = await engine.run(Worker(), context())
    assert result.status == "failed" and result.message is None


async def test_a_step_limit_leaves_its_message_on_the_result():
    """A stop that is no crash says why, for the parent of a nested run."""
    engine = engine_for([uses(fixture_call("lookup", key="k"))] * 3)
    result = await stopped_at_limit(engine, await engine.run(Worker(), context(), max_steps=2))
    assert result.stop_reason == "step_limit" and "2 steps" in result.message


async def test_a_limited_delegate_without_its_setting_is_refused():
    """``design_concurrency`` has no default: unset, the call says which variable to set."""
    session = StubSession()
    session.result = RunResult(run_id="c", status="done", answer="x")
    with runtime.settings(design_concurrency=None):
        result = await dispatch(
            Delegate(Helper(), limit="design_concurrency"), call(), Context(session=session)
        )
    assert result.is_error and "GEOMIND_DESIGN_CONCURRENCY" in result.output["error"]["message"]


async def test_limited_delegates_run_at_most_the_setting_at_once():
    """Three calls with a limit of two: never more than two nested runs at the same time."""
    import asyncio

    running, most = [0], [0]

    class Session(StubSession):
        async def delegate(self, agent, task):
            running[0] += 1
            most[0] = max(most[0], running[0])
            await asyncio.sleep(0.01)
            running[0] -= 1
            return RunResult(run_id="c", status="done", answer=task)

    session = Session()
    delegate = Delegate(Helper(), limit="design_concurrency")
    with runtime.settings(design_concurrency=2):
        results = await asyncio.gather(
            *(dispatch(delegate, call(f"t{n}"), Context(session=session)) for n in range(3))
        )
    assert [result.output for result in results] == ["t0", "t1", "t2"] and most[0] == 2
