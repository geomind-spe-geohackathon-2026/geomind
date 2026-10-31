"""Calling a tool as the engine does, for tests of the gemini tools."""

import json

from geomind.engine import Context
from geomind.tools import dispatch
from geomind.types import ToolCall
from tests.fixtures.sessions import StubSession


async def call(tool, tool_input, session=None, project=None, problem=None):
    """Dispatch one call and return its result, checking it is plain JSON and no bug.

    ``problem`` is the problem state the tool reads, such as one with a brief.
    """
    session = session or StubSession()
    options = {} if problem is None else {"problem": problem}
    context = Context(project=project, session=session, **options)
    result = await dispatch(tool, ToolCall(id="c1", name=tool.name, input=tool_input), context)
    assert session.errors == []
    json.dumps(result.output, allow_nan=False)
    return result
