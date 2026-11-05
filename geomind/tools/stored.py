"""Large tool results kept by reference, the short form the model reads, and the tool for it.

A result longer than ``STORE_CHARACTERS`` is saved as the chat artifact ``result-<hash of the call
id>``. The model reads it whole in the step after the call; from the next step on, and at once when
it is longer than the ``tool_result_limit`` setting, it reads ``stored_form``: the reference, the
small top-level values and an outline of the rest. ``read_stored`` returns the whole, or one part.
"""

import hashlib
import json

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.utils.json import to_jsonable

STORE_CHARACTERS = 2000
SHOWN_INDEXES = 10
"""How many list indexes a wrong path lists."""
SUMMARY_CHARACTERS = 600
SMALL_CHARACTERS = 150
MINIMUM_SHARE = 40
INPUT_CHARACTERS = 800
NAME_KEYS = ("name", "id")
RESERVED = ("reference", "summary")


def reference_of(call_id):
    """Return the artifact key of the result of a call; a call id never becomes part of a path."""
    return f"result-{hashlib.sha256(call_id.encode()).hexdigest()[:16]}"


def is_stored_form(output, reference):
    """Tell whether an output already is the short form of ``reference``."""
    return isinstance(output, dict) and output.get("reference") == reference and "summary" in output


def _cut(text, budget):
    """Return the text within the budget, marked when cut."""
    return text if len(text) <= budget else text[: max(budget - 1, 0)] + "…"


def _list_outline(items, budget):
    """Return a list as its length and its names, or its length and its first item."""
    names = [
        item[key]
        for item in items
        if isinstance(item, dict)
        for key in NAME_KEYS[:1]
        if key in item
    ]
    if names and len(names) == len(items):
        return _cut(f"[{len(items)} items: {', '.join(map(str, names))}]", budget)
    return _cut(f"[{len(items)} items; first: {outline(items[0], budget // 2)}]", budget)


def _dict_outline(mapping, budget):
    """Return a mapping with the outline of each value, or only its keys when they do not fit."""
    share = budget // max(len(mapping), 1)
    if share < MINIMUM_SHARE:
        return _cut(f"{{{len(mapping)} keys: {', '.join(map(str, mapping))}}}", budget)
    parts = [f"{json.dumps(key)}: {outline(value, share)}" for key, value in mapping.items()]
    return "{" + ", ".join(parts) + "}"


def outline(value, budget=SUMMARY_CHARACTERS):
    """Return a short text that shows the shape of a JSON value and what is small in it.

    Whatever fits the budget is shown whole; a longer list shows its length and names (or its first
    item), a longer mapping the outline of each value or, with too many keys, the keys alone.
    """
    text = json.dumps(value)
    if len(text) <= budget:
        return text
    if isinstance(value, dict):
        return _dict_outline(value, budget)
    if isinstance(value, list) and value:
        return _list_outline(value, budget)
    return _cut(text, budget)


def stored_form(output, reference):
    """Return what the model reads in place of a stored result: the reference and an outline.

    A mapping keeps its small top-level values under their own keys, so what the model needs first
    (a name, a count, the project's files) stays in reach, and ``summary`` outlines the whole.
    """
    kept = {}
    rest = output
    if isinstance(output, dict):
        kept = {
            key: value
            for key, value in output.items()
            if key not in RESERVED and len(json.dumps(value)) <= SMALL_CHARACTERS
        }
        rest = {key: value for key, value in output.items() if key not in kept}
    told = output.get("note") if isinstance(output, dict) else None
    return {
        **kept,
        **({"answer_note": told} if isinstance(told, str) else {}),
        "reference": reference,
        "summary": outline(rest),
        "note": "read_stored(reference)",
    }


def is_long(arguments):
    """Tell whether the arguments of a call are too long to stay in the history after the call."""
    return len(json.dumps(arguments)) > INPUT_CHARACTERS


PLACEHOLDER = "shortened"
"""The key an old history wrote a long call's outline under, as if it were the call's input."""


def shortened(call):
    """Return a call whose long arguments are left out, once the call is old: its input is empty.

    The call was made and its result read; what it changed is stored by the tool, which reads it
    back (``read_plant``, ``read_case``, ``read_profile``), so the history keeps the shape only,
    and in the message's text (``shortened_note``), not as input a model could send again.
    """
    if not is_long(call.input):
        return call
    return call.model_copy(update={"input": {}})


def shortened_note(call):
    """Return the line that stands for a long call's arguments in the text of its message."""
    shape = outline(call.input, INPUT_CHARACTERS // 2)
    return (
        f"[{call.name} was called with long arguments, left out of this history: {shape}. "
        "They are no input to send again.]"
    )


def shortened_message(message):
    """Return an old assistant message with each long call input left out and outlined in text."""
    notes = [shortened_note(call) for call in message.tool_calls if is_long(call.input)]
    if not notes:
        return message
    text = "\n".join(part for part in (message.content or "", *notes) if part)
    return message.model_copy(
        update={"content": text, "tool_calls": tuple(map(shortened, message.tool_calls))}
    )


def is_placeholder(tool, tool_input):
    """Tell whether a call's input is the outline an old history showed of an earlier call."""
    properties = tool.input_schema.get("properties") or {}
    return (
        isinstance(tool_input, dict)
        and set(tool_input) == {PLACEHOLDER}
        and PLACEHOLDER not in properties
    )


def placeholder_error(tool):
    """Return the error of a call that sent an earlier call's outline as its input."""
    names = list((tool.input_schema.get("properties") or {}).keys())
    expected = f"its arguments are {', '.join(names)}" if names else "it takes no arguments"
    return ToolError(
        f"{tool.name}: input = {{{PLACEHOLDER!r}: ...}}, the outline of an earlier call in the "
        f"shortened history, not arguments; {expected}. Send the call with its real arguments",
        code="invalid_input",
        path=PLACEHOLDER,
        suggestions=names,
    )


def _step(value, part, walked=""):
    """Return one part of a stored value: a mapping key or a list index.

    A part that is not there names the path walked, what may come next there as whole paths and,
    for an answer with ``tables``, each table's path; never the value's text, which filled the
    error when it was outlined.
    """
    if isinstance(value, dict) and part in value:
        return value[part]
    if (
        isinstance(value, list)
        and part.lstrip("-").isdigit()
        and -len(value) <= int(part) < len(value)
    ):
        return value[int(part)]
    prefix = f"{walked}." if walked else ""
    tables = tables_in(value) if not walked else []
    message = f"read_stored: path = {prefix}{part}; {part!r} is no key or index of "
    message += walked or "the result"
    if not walked:
        message += (
            " (a key the tool's answer showed beside its `reference`, such as `plants_need`, is in "
            "that answer itself, not in the stored result)"
        )
    names = [name for name in parts_of(value) if name != TEXT_HINT]
    message += f"; expected one of {', '.join(names)}" if names else ""
    message += f"; {TEXT_HINT}" if isinstance(value, str) else ""
    if isinstance(value, list):
        message += f" (a list of {len(value)})"
    if tables:
        message += "; its tables: " + ", ".join(
            f"{table['path']} ({table['rows']} rows)" if "rows" in table else table["path"]
            for table in tables
        )
    raise ToolError(
        message,
        code="unknown_name",
        path="path",
        suggestions=[table["path"] for table in tables] + [f"{prefix}{name}" for name in names]
        or parts_of(value),
    )


def tables_in(value):
    """Return the ``tables`` of a stored answer that names them, each with its ``path``."""
    found = value.get("tables") if isinstance(value, dict) else None
    if not isinstance(found, list):
        return []
    return [
        table for table in found if isinstance(table, dict) and isinstance(table.get("path"), str)
    ]


TEXT_HINT = "the value is text: read_stored without a path"
"""How to read a stored text, which a path cannot name a part of."""


def parts_of(value):
    """Return what a path may name next in a stored value: keys, first indexes, or a text hint."""
    if isinstance(value, dict):
        return [str(key) for key in value]
    if isinstance(value, list):
        return [str(index) for index in range(min(len(value), SHOWN_INDEXES))]
    if isinstance(value, str):
        return [TEXT_HINT]
    return []


@tool(effect="read", stored_input="reference", keeps_result=True)
def read_stored(context, reference: str, path: str | None = None):
    """Return a result that was stored by reference, whole or one part of it.

    Skill `reading-results`.
    """
    stored = context.session.load_artifact(reference)
    if stored is None:
        raise ToolError(
            f"read_stored: reference = {reference!r}; expected a result-... key that a result gave",
            code="unknown_name",
            path="reference",
        )
    path = (path or "").replace("/", ".").strip(".")
    walked = []
    for part in path.split("."):
        stored = _step(stored, part, ".".join(walked)) if part else stored
        walked += [part] if part else []
    value = to_jsonable(stored)
    if len(json.dumps(value)) <= runtime.get("tool_result_limit"):
        return value
    return deeper(reference, path, value)


def deeper(reference, path, value):
    """Return the keys or length of a part too long to show, with the call that reads one."""
    keys = parts_of(value)
    first = keys[0] if keys else "0"
    prefix = f"{path}." if path else ""
    return {
        "reference": reference,
        "path": path or None,
        "keys": keys,
        "summary": outline(value),
        "note": (
            "too long to show whole: read one part, such as "
            f"read_stored(reference={reference!r}, path='{prefix}{first}')"
        ),
    }
