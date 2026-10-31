"""Checks of a tool that exists only as its final signature."""

from geomind.engine import Context
from geomind.tools import dispatch
from geomind.types import ToolCall
from tests.fixtures.sessions import StubSession


async def check_stub(tool, tool_input, effect, phase):
    """Check that a valid call is a ``not_implemented`` result naming the phase, and no bug."""
    session = StubSession()
    call = ToolCall(id="c1", name=tool.name, input=tool_input)
    result = await dispatch(tool, call, Context(session=session))
    problem = result.output["error"]
    assert result.is_error and not result.is_validation
    assert problem["code"] == "not_implemented"
    assert f"{tool.name} comes in {phase}" in problem["message"]
    assert tool.effect == effect
    assert tool.description
    assert session.errors == []
