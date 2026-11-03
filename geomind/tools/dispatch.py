"""Run one tool call: one of the two places with side effects."""

import asyncio
import inspect
import json
import re
from time import perf_counter

import pydantic

from geomind import runtime
from geomind.errors import (
    GeomindError,
    NotImplementedYet,
    ToolError,
    UnknownNameError,
)
from geomind.tools.stored import STORE_CHARACTERS, reference_of, stored_form
from geomind.types import Finish, Problem, Request, ToolResult
from geomind.utils.json import to_jsonable

MARKUP = re.compile(r"</|<(?:parameter|invoke|function_calls|function)\b|^\s*\"?>")
"""Tool-call markup a model leaks into an argument's value instead of ending the value (#70)."""

PROSE_TOOLS = frozenset({"finish", "ask_user", "update_state", "write_lesson"})
"""Tools whose inputs are prose, where ``</`` may be meant: no markup check for them."""

CODE_OF_ERROR = {
    NotImplementedYet: "not_implemented",
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
    """Return the problem of an input that does not fit: its first field, with the whole text.

    An object sent as JSON text, which models often do, gets the suggestion to send the object.
    """
    first = error.errors()[0]
    path = ".".join(str(field) for field in first["loc"]) or None
    suggestions = (
        [f"{path} is JSON text: send the object itself, not a string"]
        if (first["type"] == "dict_type" and _is_json_object(first.get("input")))
        else []
    )
    return Problem(path=path, code="invalid_input", message=str(error), suggestions=suggestions)


def _is_json_object(value):
    """Tell whether ``value`` is text that reads as a JSON object."""
    if not isinstance(value, str):
        return False
    try:
        return isinstance(json.loads(value), dict)
    except ValueError:
        return False


def _problem(error):
    """Return the problem of a geomind error or an input that does not fit."""
    if isinstance(error, pydantic.ValidationError):
        return _validation_problem(error)
    if isinstance(error, ToolError):
        return Problem(
            path=error.path, code=error.code, message=str(error), suggestions=error.suggestions
        )
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


def seconds_of(tool, context):
    """Return the seconds a call may take: its tool's timeout, or less when the run has less."""
    left = getattr(context.session, "time_left", None)
    limits = [seconds for seconds in (tool.timeout, left) if seconds is not None]
    return min(limits) if limits else None


def timed_out(tool, context):
    """Return the error of a call that timed out; one the time limit cut also ends the run."""
    left = getattr(context.session, "time_left", None)
    if left is None or (tool.timeout is not None and tool.timeout <= left):
        return ToolError(f"{tool.name}: timed out after {tool.timeout} s", code="timeout")
    reason = f"time limit: {tool.name} passed the time the run had left"
    context.session.note_limit(reason)
    return ToolError(reason, code="timeout")


async def _call(tool, arguments, context):
    """Run the function with its timeout; a sync one runs in a worker thread."""
    leading = (context,) if tool.takes_context else ()
    async with asyncio.timeout(seconds_of(tool, context)):
        if inspect.iscoroutinefunction(tool.function):
            return await tool.function(*leading, **arguments)
        return await runtime.in_gemini_thread(tool.function, *leading, **arguments)


async def _bounded(context, call, output, tool=None):
    """Return the output for the model, saving a long one as an artifact.

    A result over ``STORE_CHARACTERS`` is stored and carries its reference, whole while it is fresh;
    one over ``tool_result_limit`` reaches the model only as ``stored_form``. A part of a stored
    result (``Tool.stored_input``) keeps the reference it was read from and is not stored again,
    and the history keeps a tool's result whole for a few turns when it keeps its results
    (``Tool.keeps_result``).
    """
    text = json.dumps(output)
    limit = runtime.get("tool_result_limit")
    if len(text) <= min(STORE_CHARACTERS, limit):
        return output, None
    source = getattr(tool, "stored_input", None)
    key = call.input.get(source) if source else None
    if key is None:
        key = reference_of(call.id)
        await context.session.save_artifact(key, output)
    if len(text) <= limit:
        return output, key
    return stored_form(output, key), key


def _result(tool, call, started, output, **fields):
    """Return one result with its duration."""
    duration = perf_counter() - started
    return ToolResult(call_id=call.id, tool=tool.name, output=output, duration=duration, **fields)


def leaked_markup(value, path=""):
    """Return ``(path, value)`` of the first string of an input holding tool-call markup."""
    if isinstance(value, str):
        return (path or None, value) if MARKUP.search(value) else None
    if not isinstance(value, (dict, list, tuple)):
        return None
    items = value.items() if isinstance(value, dict) else enumerate(value)
    for key, item in items:
        found = leaked_markup(item, f"{path}.{key}" if path else str(key))
        if found is not None:
            return found
    return None


def markup_error(tool, found):
    """Return the error of a value with leaked markup, suggesting the value before it (#70).

    NOTE: it is no validation failure, which two in a row end the run: the call is right but for
    a slip of the model's formatting, and the next call is usually clean (#75).
    """
    path, value = found
    guess = value.split("<", 1)[0].strip().strip('">').strip()
    return ToolError(
        f"{tool.name}: {path} = {value[:80]!r}...; it holds tool-call markup, not only the "
        "value: send the call again with the value alone",
        code="invalid_input",
        path=path,
        suggestions=[guess] if guess else [],
    )


async def dispatch(tool, call, context):
    """Validate, run and time one call.

    Returns a ``ToolResult``, or the ``Request`` or ``Finish`` the tool returned for the engine.
    An error the model can act on becomes a result with ``is_error``; any other exception is
    reported through the run and the model reads only that an internal error happened.
    """
    started = perf_counter()
    found = None if tool.name in PROSE_TOOLS else leaked_markup(call.input)
    if found is not None:
        output = error_output(markup_error(tool, found))
        return _result(tool, call, started, output, is_error=True)
    try:
        arguments = tool.validate(call.input)
    except (pydantic.ValidationError, ToolError) as error:
        output = error_output(error)
        return _result(tool, call, started, output, is_error=True, is_validation=True)
    try:
        output = await _call(tool, arguments, context.for_call(call.id))
    except TimeoutError:
        error = timed_out(tool, context)
        return _result(tool, call, started, error_output(error), is_error=True)
    except Exception as error:
        if is_reported_error(error):
            return _result(tool, call, started, error_output(error), is_error=True)
        await context.session.report_error(error, where=f"tool {tool.name}")
        hidden = ToolError(f"{tool.name}: internal error", code="internal")
        return _result(tool, call, started, error_output(hidden), is_error=True)
    if isinstance(output, (Request, Finish)):
        return output
    bounded, reference = await _bounded(context, call, to_jsonable(output), tool)
    return _result(tool, call, started, bounded, reference=reference)
