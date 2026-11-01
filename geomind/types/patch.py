"""JSON Patch operations on the problem state, the subset the contract allows."""

import re
from typing import Any, Literal

from geomind.types.messages import Record

OPERATIONS = ("add", "replace", "remove")
STATE_KEYS = (
    "goal",
    "requirements",
    "assumptions",
    "design",
    "results",
    "verification",
    "questions",
    "case",
    "case_origin",
)
ITEM_LISTS = ("requirements", "assumptions", "results", "questions")
_POINTER = re.compile(r"^(/([^~/]|~0|~1)*)+$")


class PatchOperation(Record):
    """One JSON Patch operation; ``value`` is absent on a ``remove``."""

    op: Literal["add", "replace", "remove"]
    path: str
    value: Any = None


class StateChange(Record):
    """The JSON of ``state.changed``: the version after the change, and the operations."""

    version: int
    changes: tuple[PatchOperation, ...]


def _path_problem(operation, path):
    """Return what is wrong with a JSON Pointer of this operation, or ``None``."""
    if not isinstance(path, str) or not _POINTER.match(path):
        return f"path = {path!r}; expected a JSON Pointer"
    tokens = path.split("/")[1:]
    if tokens[0] not in STATE_KEYS:
        return f"path = {path!r}; expected a top-level key of the problem state"
    if "-" in tokens[:-1] or (tokens[-1] == "-" and operation != "add"):
        return f"path = {path!r}; '-' appends, so it ends the path of an add"
    return None


def _value_problem(change):
    """Return what is wrong with the value of an operation, or ``None``."""
    is_remove = change.get("op") == "remove"
    if is_remove == ("value" in change):
        return f"{change}; expected a value for add and replace, and none for remove"
    tokens = change["path"].split("/")[1:]
    is_item = tokens[0] in ITEM_LISTS and tokens[1:] == ["-"]
    if is_item and "id" not in (change["value"] if isinstance(change["value"], dict) else ()):
        return f"{change}; an item appended to {tokens[0]} needs an id"
    return None


def operation_problem(change):
    """Return what is wrong with one operation, or ``None`` when it is valid."""
    if not isinstance(change, dict) or not set(change) <= {"op", "path", "value"}:
        return f"change = {change!r}; expected only op, path and value"
    if change.get("op") not in OPERATIONS:
        return f"op = {change.get('op')!r}; expected add, replace or remove"
    return _path_problem(change["op"], change.get("path")) or _value_problem(change)
