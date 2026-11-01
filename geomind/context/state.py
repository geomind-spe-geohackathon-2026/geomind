"""The problem state: shared notes kept outside the message window."""

import json
from typing import Any, Literal

from pydantic import ValidationError, model_validator

from geomind.errors import StateError
from geomind.types import Record
from geomind.types.patch import ITEM_LISTS, operation_problem
from geomind.utils.strings import did_you_mean, join_names


class Requirement(Record):
    """A criterion of the task, in the user's words.

    A numeric one is a constraint of the case (``set_case``), and ``constraint`` is the index of
    that constraint in ``case.constraints``; gemini judges it, the text is never parsed.
    """

    id: str
    text: str
    constraint: int | None = None
    status: str = "open"


class Assumption(Record):
    """A value the work relies on, and where it came from."""

    id: str
    text: str
    value: Any = None
    source: Literal["user", "agent", "default"] = "agent"
    confirmed: bool = False


class Result(Record):
    """A finding; ``reference`` names the stored full data."""

    id: str
    summary: str
    reference: str | None = None


class Question(Record):
    """An open question for the user."""

    id: str
    text: str


class Compaction(Record):
    """The summary of the first ``turns`` turns of a chat's history."""

    summary: str
    turns: int


class ProblemState(Record):
    """The notes of one chat; ``version`` is raised by one with every change.

    NOTE: the state is frozen, so a change is always a new state and the only writer is ``apply`` of
    the engine, over events. NOTE: ``compaction`` is kept here because ``save_state`` is the only
    per-chat storage of the contract, and ``load_history`` always returns every message. It is no
    key of the document: a patch cannot reach it and ``render`` does not show it.
    """

    version: int = 0
    goal: str = ""
    requirements: tuple[Requirement, ...] = ()
    assumptions: tuple[Assumption, ...] = ()
    design: dict[str, Any] = {}
    results: tuple[Result, ...] = ()
    verification: dict[str, Any] = {}
    questions: tuple[Question, ...] = ()
    case: dict[str, Any] | None = None
    compaction: Compaction | None = None

    @model_validator(mode="after")
    def _check_ids(self):
        """Refuse two items with one id, since a path names an item by its id."""
        for name in ITEM_LISTS:
            ids = [item.id for item in getattr(self, name)]
            repeated = sorted({item for item in ids if ids.count(item) > 1})
            if repeated:
                raise ValueError(f"{name}: ids = {repeated}; expected each id once")
        return self


def _item(items, token, path):
    """Return the item of an id-addressed list."""
    for item in items:
        if isinstance(item, dict) and item.get("id") == token:
            return item
    ids = [item["id"] for item in items if isinstance(item, dict) and "id" in item]
    raise StateError(
        f"update_state: path = {path!r}; expected the id of an item, one of {join_names(ids)}"
        f"{did_you_mean(token, ids)}"
    )


def _child(node, token, path):
    """Return what ``token`` names inside ``node``."""
    if isinstance(node, list):
        return _item(node, token, path)
    if isinstance(node, dict) and token in node:
        return node[token]
    raise StateError(f"update_state: path = {path!r}; {token!r} does not exist there")


def _change_item(items, change, token):
    """Apply one operation to an id-addressed list."""
    path = change["path"]
    if change["op"] == "add":
        if token != "-":
            raise StateError(f"update_state: path = {path!r}; expected '-' to append an item")
        items.append(change["value"])
        return
    position = items.index(_item(items, token, path))
    if change["op"] == "replace":
        items[position] = change["value"]
        return
    del items[position]


def _change_key(node, change, token):
    """Apply one operation to a mapping."""
    path = change["path"]
    if not isinstance(node, dict):
        raise StateError(f"update_state: path = {path!r}; expected a path into an object")
    if change["op"] == "add":
        node[token] = change["value"]
        return
    _child(node, token, path)
    if change["op"] == "replace":
        node[token] = change["value"]
        return
    del node[token]


def _apply_one(document, change):
    """Apply one valid operation to the document."""
    path = change["path"]
    tokens = [token.replace("~1", "/").replace("~0", "~") for token in path.split("/")[1:]]
    node = document
    for token in tokens[:-1]:
        node = _child(node, token, path)
    if isinstance(node, list):
        _change_item(node, change, tokens[-1])
        return
    _change_key(node, change, tokens[-1])


def _problems(error):
    """Return the validation errors of a state as one line."""
    return "; ".join(f"{'/'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors())


def _validated(document):
    """Return the state a document describes, or raise what the model must fix."""
    try:
        return ProblemState.model_validate(document)
    except ValidationError as error:
        raise StateError(f"update_state: {_problems(error)}") from error


def apply_changes(state, changes):
    """Return a new state with the JSON Patch ``changes`` applied and ``version + 1``.

    The whole patch applies or none of it. An invalid patch raises ``StateError`` with a message
    that tells the model how to fix it. NOTE: each operation is validated at once, so the next one
    can address the default fields of an item just appended.
    """
    if not changes:
        raise StateError("update_state: changes = []; expected at least one operation")
    current = state
    for change in changes:
        problem = operation_problem(change)
        if problem is not None:
            raise StateError(f"update_state: {problem}")
        document = current.model_dump(mode="json")
        _apply_one(document, change)
        current = _validated(document)
    return current.model_copy(update={"version": state.version + 1})


def _requirement_line(item):
    """Return one requirement as a line."""
    linked = f" (case constraint {item.constraint})" if item.constraint is not None else ""
    return f"Requirement {item.id} [{item.status}]: {item.text}{linked}"


def _assumption_line(item):
    """Return one assumption as a line."""
    status = "confirmed" if item.confirmed else "unconfirmed"
    value = f" = {json.dumps(item.value)}" if item.value is not None else ""
    return f"Assumption {item.id} [{status}, {item.source}]: {item.text}{value}"


def _result_line(item):
    """Return one result as a line."""
    reference = f" ({item.reference})" if item.reference else ""
    return f"Result {item.id}: {item.summary}{reference}"


def _case_line(case):
    """Return the case as one line: its time and its sections, never the demand itself."""
    time = case.get("time") or {}
    span = f"{time.get('start')} to {time.get('end')}"
    sections = ", ".join(name for name in case if name != "time")
    demand = case.get("demand") or {}
    served = [name for name in ("heating", "cooling") if name in demand]
    line = f"Case: time {span}; sections {sections or 'none'}"
    return f"{line}; demand {', '.join(served)} in {demand.get('file')}" if served else line


def render(state):
    """Return compact text, one line per item, or ``""`` for an untouched state."""
    if state.version == 0:
        return ""
    lines = [f"Problem state, version {state.version}"]
    if state.goal:
        lines.append(f"Goal: {state.goal}")
    lines += [_requirement_line(item) for item in state.requirements]
    lines += [_assumption_line(item) for item in state.assumptions]
    if state.design:
        lines.append(f"Design: {json.dumps(state.design)}")
    lines += [_result_line(item) for item in state.results]
    if state.verification:
        lines.append(f"Verification: {json.dumps(state.verification)}")
    lines += [f"Question {item.id}: {item.text}" for item in state.questions]
    if state.case is not None:
        lines.append(_case_line(state.case))
    return "\n".join(lines)
