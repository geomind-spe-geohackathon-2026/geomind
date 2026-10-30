"""Dispatch: validation, timing, errors, timeouts and large results."""

import asyncio

import pytest

from swarmax.core import runtime
from swarmax.core.types import Finish, Request, ToolCall
from swarmax.errors import ToolError
from swarmax.tools import ask_user, dispatch, finish, tool
from swarmax.tools.dispatch import is_reported_error
from tests.fixtures.sessions import StubSession


@pytest.fixture
def session():
    """Activate a stand-in run."""
    stub = StubSession()
    with runtime.activate(stub):
        yield stub


@tool(effect="compute")
def add(left: int, right: int):
    """Add."""
    return left + right


@tool(effect="read")
async def echo(text: str):
    """Echo."""
    return text


@tool(effect="read")
def active_run_id():
    """Read the active run from a worker thread."""
    return id(runtime.active_run())


@tool(effect="read", timeout=0.01)
async def slow():
    """Sleep too long."""
    await asyncio.sleep(5)


@tool(effect="read")
def raises_tool_error():
    """Fail on purpose."""
    raise ToolError("bad parameter")


@tool(effect="read")
def raises_bug():
    """Have a bug."""
    raise ZeroDivisionError("secret detail")


def call(name="add", **tool_input):
    """Return one call."""
    return ToolCall(id="c1", name=name, input=tool_input)


async def test_sync_and_async_functions_run(session):
    """Both kinds return a timed result."""
    result = await dispatch(add, call(left=1, right=2))
    assert (result.output, result.is_error, result.call_id) == (3, False, "c1")
    assert result.duration >= 0
    assert (await dispatch(echo, call(text="hi"))).output == "hi"


async def test_sync_tool_sees_the_active_run_in_its_worker(session):
    """A worker thread receives a copied context."""
    assert (await dispatch(active_run_id, call())).output == id(session)


async def test_validation_error_is_a_result_for_the_model(session):
    """A wrong call is marked so the engine can count it."""
    result = await dispatch(add, call(left="x", right=1))
    assert result.is_error and result.is_validation
    assert result.output["error"]["class"] == "ValidationError"


async def test_swarmax_error_is_a_result(session):
    """A deliberate error reaches the model with class and message."""
    result = await dispatch(raises_tool_error, call())
    assert result.is_error and not result.is_validation
    assert result.output == {"error": {"class": "ToolError", "message": "bad parameter"}}


async def test_gemini_error_is_a_result(session):
    """Errors of gemini are recognised by their class path, without importing gemini here."""

    class UnitError(ValueError):
        """Stand-in for a gemini error."""

    UnitError.__module__ = "gemini.errors.physics"
    assert is_reported_error(UnitError("bad unit"))


async def test_bug_is_reported_and_hidden_from_the_model(session):
    """A bug goes to ``on_error``, and the model reads only that it happened."""
    result = await dispatch(raises_bug, call())
    assert result.is_error and "internal error" in result.output["error"]["message"]
    assert "secret detail" not in str(result.output)
    assert isinstance(session.errors[0][0], ZeroDivisionError)


async def test_timeout_is_an_error_result(session):
    """A tool over its time limit is stopped."""
    result = await dispatch(slow, call())
    assert result.is_error and "timed out" in result.output["error"]["message"]


async def test_large_result_is_an_artifact(session):
    """The model sees a reference and a summary; the store holds the data."""
    with runtime.settings(tool_result_limit=10):
        result = await dispatch(echo, call(text="x" * 100))
    assert result.reference == result.output["reference"]
    assert session.artifacts[result.reference] == "x" * 100
    assert len(result.output["summary"]) < 200


async def test_artifact_key_is_safe_for_any_call_id(session):
    """A call id comes from the model, so it never becomes part of a path."""
    bad = ToolCall(id="../../etc/passwd", name="echo", input={"text": "x" * 100})
    with runtime.settings(tool_result_limit=10):
        result = await dispatch(echo, bad)
    assert "/" not in result.reference


async def test_builtins_return_what_the_engine_understands(session):
    """A question and a final answer pass through unchanged."""
    request = await dispatch(ask_user, call(question="which?", options=["a"]))
    assert isinstance(request, Request) and request.options == ("a",)
    assert await dispatch(finish, call(answer="done")) == Finish(answer="done")
