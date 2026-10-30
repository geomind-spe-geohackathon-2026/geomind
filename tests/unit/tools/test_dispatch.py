"""Dispatch: validation, timing, errors, timeouts and large results."""

import asyncio

import pytest

from geomind import runtime
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.tools import ask_user, dispatch, finish, tool
from geomind.tools.dispatch import is_reported_error
from geomind.types import Finish, Request, ToolCall
from tests.fixtures.sessions import StubSession


@pytest.fixture
def session():
    """Return a stand-in run."""
    return StubSession()


@pytest.fixture
def context(session):
    """Return a context of the stand-in run."""
    return Context(session=session)


@tool(effect="compute")
def add(left: int, right: int):
    """Add."""
    return left + right


@tool(effect="read")
async def echo(text: str):
    """Echo."""
    return text


@tool(effect="read")
def session_id(context):
    """Read the run from a worker thread."""
    return id(context.session)


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


async def test_sync_and_async_functions_run(session, context):
    """Both kinds return a timed result."""
    result = await dispatch(add, call(left=1, right=2), context)
    assert (result.output, result.is_error, result.call_id) == (3, False, "c1")
    assert result.duration >= 0
    assert (await dispatch(echo, call(text="hi"), context)).output == "hi"


async def test_sync_tool_receives_the_context_in_its_worker(session, context):
    """A tool that declares ``context`` gets it, also in a worker thread."""
    assert (await dispatch(session_id, call(), context)).output == id(session)


def test_the_schema_never_shows_the_context():
    """The model sees only what it fills in."""
    assert session_id.schema()["input_schema"]["properties"] == {}
    assert session_id.takes_context and not add.takes_context


async def test_validation_error_is_a_result_for_the_model(session, context):
    """A wrong call is marked so the engine can count it."""
    result = await dispatch(add, call(left="x", right=1), context)
    assert result.is_error and result.is_validation
    assert result.output["error"]["class"] == "ValidationError"


async def test_geomind_error_is_a_result(session, context):
    """A deliberate error reaches the model with class and message."""
    result = await dispatch(raises_tool_error, call(), context)
    assert result.is_error and not result.is_validation
    assert result.output == {"error": {"class": "ToolError", "message": "bad parameter"}}


async def test_gemini_error_is_a_result(session, context):
    """Errors of gemini are recognised by their class path, without importing gemini here."""

    class UnitError(ValueError):
        """Stand-in for a gemini error."""

    UnitError.__module__ = "gemini.errors.physics"
    assert is_reported_error(UnitError("bad unit"))


async def test_bug_is_reported_and_hidden_from_the_model(session, context):
    """A bug goes to ``on_error``, and the model reads only that it happened."""
    result = await dispatch(raises_bug, call(), context)
    assert result.is_error and "internal error" in result.output["error"]["message"]
    assert "secret detail" not in str(result.output)
    assert isinstance(session.errors[0][0], ZeroDivisionError)


async def test_timeout_is_an_error_result(session, context):
    """A tool over its time limit is stopped."""
    result = await dispatch(slow, call(), context)
    assert result.is_error and "timed out" in result.output["error"]["message"]


async def test_large_result_is_an_artifact(session, context):
    """The model sees a reference and a summary; the store holds the data."""
    with runtime.settings(tool_result_limit=10):
        result = await dispatch(echo, call(text="x" * 100), context)
    assert result.reference == result.output["reference"]
    assert session.artifacts[result.reference] == "x" * 100
    assert len(result.output["summary"]) < 200


async def test_artifact_key_is_safe_for_any_call_id(session, context):
    """A call id comes from the model, so it never becomes part of a path."""
    bad = ToolCall(id="../../etc/passwd", name="echo", input={"text": "x" * 100})
    with runtime.settings(tool_result_limit=10):
        result = await dispatch(echo, bad, context)
    assert "/" not in result.reference


async def test_builtins_return_what_the_engine_understands(session, context):
    """A question and a final answer pass through unchanged."""
    request = await dispatch(ask_user, call(question="which?", options=["a"]), context)
    assert isinstance(request, Request) and request.options[0].value == "a"
    assert await dispatch(finish, call(answer="done"), context) == Finish(answer="done")
