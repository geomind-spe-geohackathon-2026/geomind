"""Run one tool call: one of the two places with side effects."""

import asyncio
import hashlib
import inspect
import json
from time import perf_counter

import pydantic

from swarmax.core import runtime
from swarmax.core.types import Finish, Request, ToolResult
from swarmax.errors import SwarmaxError, ToolError
from swarmax.utils.json import to_jsonable

SUMMARY_CHARACTERS = 500


def is_reported_error(error):
    """Tell whether an error is meant for the model: any ``sx.errors`` or ``gemini.errors`` class.

    NOTE: gemini is recognised by module path, because importing it costs more than a second and
    ``import swarmax`` should not pay that.
    """
    if isinstance(error, SwarmaxError):
        return True
    return any(kind.__module__.startswith("gemini.errors") for kind in type(error).__mro__)


def error_output(error):
    """Return the result a model reads for an error."""
    return {"error": {"class": type(error).__name__, "message": str(error)}}


async def _call(tool, arguments):
    """Run the function with its timeout; a sync one runs in a worker with a copied context."""
    async with asyncio.timeout(tool.timeout):
        if inspect.iscoroutinefunction(tool.function):
            return await tool.function(**arguments)
        return await asyncio.to_thread(tool.function, **arguments)


async def _bounded(call, output):
    """Return the output for the model, saving a large one as an artifact."""
    text = json.dumps(output)
    if len(text) <= runtime.get("tool_result_limit"):
        return output, None
    key = f"result-{hashlib.sha256(call.id.encode()).hexdigest()[:16]}"
    await runtime.active_run().save_artifact(key, output)
    return {"reference": key, "summary": text[:SUMMARY_CHARACTERS]}, key


def _result(tool, call, started, output, **fields):
    """Return one result with its duration."""
    duration = perf_counter() - started
    return ToolResult(call_id=call.id, tool=tool.name, output=output, duration=duration, **fields)


async def dispatch(tool, call):
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
        output = await _call(tool, arguments)
    except TimeoutError:
        error = ToolError(f"{tool.name}: timed out after {tool.timeout} s")
        return _result(tool, call, started, error_output(error), is_error=True)
    except Exception as error:
        if is_reported_error(error):
            return _result(tool, call, started, error_output(error), is_error=True)
        await runtime.active_run().report_error(error, where=f"tool {tool.name}")
        hidden = ToolError(f"{tool.name}: internal error")
        return _result(tool, call, started, error_output(hidden), is_error=True)
    if isinstance(output, (Request, Finish)):
        return output
    bounded, reference = await _bounded(call, to_jsonable(output))
    return _result(tool, call, started, bounded, reference=reference)
