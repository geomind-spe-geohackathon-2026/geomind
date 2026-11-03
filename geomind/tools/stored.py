"""Large tool results kept by reference, the short form the model reads, and the tool for it.

A result longer than ``STORE_CHARACTERS`` is saved as the chat artifact ``result-<hash of the call
id>``. The model reads it whole in the step after the call; from the next step on, and at once when
it is longer than the ``tool_result_limit`` setting, it reads ``stored_form``: the reference, the
small top-level values and an outline of the rest. ``read_stored`` returns the whole, or one part.
"""

import hashlib
import json

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
    return {
        **kept,
        "reference": reference,
        "summary": outline(rest),
        "note": "read_stored(reference)",
    }


def is_long(arguments):
    """Tell whether the arguments of a call are too long to stay in the history after the call."""
    return len(json.dumps(arguments)) > INPUT_CHARACTERS


def shortened(call):
    """Return a call whose long arguments became their outline, once the call is old.

    The call was made and its result read; what it changed is stored by the tool, which reads it
    back (``read_plant``, ``read_case``, ``read_profile``), so the history keeps the shape only.
    """
    if not is_long(call.input):
        return call
    return call.model_copy(
        update={"input": {"shortened": outline(call.input, INPUT_CHARACTERS // 2)}}
    )


def _step(value, part):
    """Return one part of a stored value: a mapping key or a list index."""
    if isinstance(value, dict) and part in value:
        return value[part]
    if (
        isinstance(value, list)
        and part.lstrip("-").isdigit()
        and -len(value) <= int(part) < len(value)
    ):
        return value[int(part)]
    raise ToolError(
        f"read_stored: path = {part!r}; expected a key or index of {outline(value, 200)}",
        code="unknown_name",
        path="path",
        suggestions=parts_of(value),
    )


def parts_of(value):
    """Return what a path may name next in a stored value: its keys, or its first indexes."""
    if isinstance(value, dict):
        return [str(key) for key in value]
    if isinstance(value, list):
        return [str(index) for index in range(min(len(value), SHOWN_INDEXES))]
    return []


@tool(effect="read")
def read_stored(context, reference: str, path: str | None = None):
    """Return a result that was stored by reference, whole or one part of it.

    ``reference`` is the ``result-...`` (or ``output-...``) key of a result that came back as a
    reference and an outline. ``path`` is dotted keys and list indexes into it, such as
    ``capabilities.HeatingPlant``; a long part comes back as a reference again, so read it deeper.
    """
    stored = context.session.load_artifact(reference)
    if stored is None:
        raise ToolError(
            f"read_stored: reference = {reference!r}; expected a result-... key that a result gave",
            code="unknown_name",
            path="reference",
        )
    for part in (path or "").split("."):
        stored = _step(stored, part) if part else stored
    return to_jsonable(stored)
