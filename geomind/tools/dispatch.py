"""Run one tool call: one of the two places with side effects."""

import asyncio
import hashlib
import inspect
import json
from time import perf_counter

import pydantic

from geomind import runtime
from geomind.errors import (
    GeomindError,
    NotImplementedYet,
    SandboxError,
    ToolError,
    UnknownNameError,
)
from geomind.types import Finish, Problem, Request, ToolResult
from geomind.utils.json import to_jsonable

SUMMARY_CHARACTERS = 500
CODE_OF_ERROR = {
    NotImplementedYet: "not_implemented",
    SandboxError: "not_allowed",
    UnknownNameError: "unknown_name",
}


def is_reported_error(error):
    """Tell whether an error is meant for the model: any ``gd.errors`` or ``gemini.errors`` class.

    NOTE: gemini is recognised by module path, because importing it costs more than a second and
    ``import geomind`` should not pay that.
    """
    if isinstance(error, GeomindError):
        return True
    return any(kind.__module__.startswith("gemini.errors") for kind in type(error).__mro__)


def _validation_problem(error):
    """Return the problem of an input that does not fit: its first field, with the whole text."""
    fields = error.errors()[0]["loc"]
    path = ".".join(str(field) for field in fields) or None
    return Problem(path=path, code="invalid_input", message=str(error))


def _problem(error):
    """Return the problem of a geomind error or an input that does not fit."""
    if isinstance(error, pydantic.ValidationError):
        return _validation_problem(error)
    if isinstance(error, ToolError):
        return Problem(path=error.path, code=error.code, message=str(error))
    return Problem(code=CODE_OF_ERROR.get(type(error), "invalid_input"), message=str(error))


def error_output(error):
    """Return the result a model reads for an error, in gemini's Problem shape.

    A gemini error passes through its own ``to_dict()``; a rejected unit also lists the accepted
    ones.
    """
    if not isinstance(error, (GeomindError, pydantic.ValidationError)):
        from geomind.tools.gemini.explain import explained

        return {"error": explained(error)}
    return {"error": _problem(error).model_dump(mode="json")}


async def _call(tool, arguments, context):
    """Run the function with its timeout; a sync one runs in a worker thread."""
    leading = (context,) if tool.takes_context else ()
    async with asyncio.timeout(tool.timeout):
        if inspect.iscoroutinefunction(tool.function):
            return await tool.function(*leading, **arguments)
        return await asyncio.to_thread(tool.function, *leading, **arguments)


async def _bounded(context, call, output):
    """Return the output for the model, saving a large one as an artifact."""
    text = json.dumps(output)
    if len(text) <= runtime.get("tool_result_limit"):
        return output, None
    key = f"result-{hashlib.sha256(call.id.encode()).hexdigest()[:16]}"
    await context.session.save_artifact(key, output)
    return {"reference": key, "summary": text[:SUMMARY_CHARACTERS]}, key


def _result(tool, call, started, output, **fields):
    """Return one result with its duration."""
    duration = perf_counter() - started
    return ToolResult(call_id=call.id, tool=tool.name, output=output, duration=duration, **fields)


async def dispatch(tool, call, context):
    """Validate, run and time one call.

    Returns a ``ToolResult``, or the ``Request`` or ``Finish`` the tool returned for the engine.
    An error the model can act on becomes a result with ``is_error``; any other exception is
    reported through the run and the model reads only that an internal error happened.
    """
    started = perf_counter()
    try:
        arguments = tool.validate(call.input)
    except (pydantic.ValidationError, ToolError) as error:
        output = error_output(error)
        return _result(tool, call, started, output, is_error=True, is_validation=True)
    try:
        output = await _call(tool, arguments, context.for_call(call.id))
    except TimeoutError:
        error = ToolError(f"{tool.name}: timed out after {tool.timeout} s", code="timeout")
        return _result(tool, call, started, error_output(error), is_error=True)
    except Exception as error:
        if is_reported_error(error):
            return _result(tool, call, started, error_output(error), is_error=True)
        await context.session.report_error(error, where=f"tool {tool.name}")
        hidden = ToolError(f"{tool.name}: internal error", code="internal")
        return _result(tool, call, started, error_output(hidden), is_error=True)
    if isinstance(output, (Request, Finish)):
        return output
    bounded, reference = await _bounded(context, call, to_jsonable(output))
    return _result(tool, call, started, bounded, reference=reference)
