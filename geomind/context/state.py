"""The problem state: shared notes kept outside the message window."""

import json
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator

from geomind.errors import StateError
from geomind.types import Record
from geomind.types.patch import ITEM_LISTS, operation_problem
from geomind.utils.strings import did_you_mean, join_names


class Requirement(Record):
    """A criterion of the task, in the user's words.

    A numeric one is a requirement of the case (``set_case``), and ``case_requirement`` names it by
    its ``name``; gemini judges it, the text is never parsed.
    """

    id: str
    text: str
    case_requirement: str | None = None
    status: str = "open"


class Assumption(Record):
    """A value the work relies on, and where it came from.

    ``reason`` says why a value was chosen; ``citation`` holds the details of a published source,
    such as ``title``, ``publisher``, ``year``, ``price_year``, ``currency``, ``page`` or ``link``
    and a ``note``, so the explainer and the export can show them.
    """

    id: str
    text: str
    value: Any = None
    source: Literal["user", "agent", "default"] = "agent"
    confirmed: bool = False
    reason: str | None = None
    citation: dict[str, Any] | None = None


class Result(Record):
    """A finding; ``reference`` names the stored full data."""

    id: str
    summary: str
    reference: str | None = None


class Question(Record):
    """An open question for the user."""

    id: str
    text: str


class Calculation(Record):
    """A derived value ``calculate`` stored: its result, the expression and every operand's source.

    ``operands`` holds, per operand, the reference given, its value and unit, and its ``source``
    (the case path, the catalogue row with its citation, the approved assumption, the stored result
    or the earlier calculation), so the report can cite the chain.
    """

    id: str
    label: str
    operation: str
    expression: str
    value: Any
    unit: str
    operands: tuple[dict[str, Any], ...] = ()
    code: str | None = None


class Compaction(Record):
    """The summary of the first ``turns`` turns of a chat's history."""

    summary: str
    turns: int


REFERENCE_PATTERN = r"^(design|result)/[^/]+$"
Reference = Annotated[str, Field(json_schema_extra={"pattern": REFERENCE_PATTERN})]
REFERENCE_FIELDS = {"reference": "reference", "result": "result", "start_result": "reference"}


class Alternative(BaseModel):
    """A family of a comparison: its design and result, its ``verdict`` and the ``reason``.

    ``verdict`` is ``feasible`` or ``infeasible`` as its run recorded, then ``verified`` or
    ``rejected`` as gemini judged it, ``failed`` for a run that left no design and ``blocked`` for
    a family gemini cannot build. A state stored before 0.4.6 has neither key.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    family: str | None = None
    design: Reference | None = None
    result: Reference | None = None
    verdict: str | None = None
    reason: str | None = None


class DesignState(BaseModel):
    """The design section of the state: references are strings, not objects.

    ``reference`` is the final design (``design/<name>``), ``result`` its whole-year run and
    ``start_result`` the sized start's run (``result/<id>``); ``alternatives`` lists the other
    families as ``{family, design, result}``. Other keys (``families``, ``family``, ``schematic``,
    ``study``, ``rejected``) are free. The pattern is advertised, not enforced, so a state stored
    before it still loads.
    """

    model_config = ConfigDict(frozen=True, extra="allow")

    reference: Reference | None = None
    result: Reference | None = None
    start_result: Reference | None = None
    alternatives: tuple[Alternative, ...] | None = None


def converted(value, key):
    """Return the reference a 0.4.x object carries (``{key: ...}`` or ``reference``), else None."""
    if not isinstance(value, dict):
        return None
    found = value.get(key) or value.get("reference")
    return found if isinstance(found, str) else None


def convert_fields(document, names, unreadable, prefix=""):
    """Convert each object in ``document[name]`` (``names`` maps a field to its key), in place."""
    for name, key in names.items():
        if not isinstance(document.get(name), dict):
            continue
        value = document.pop(name)
        found = converted(value, key)
        if found is None:
            unreadable[f"{prefix}{name}"] = value
        else:
            document[name] = found


def old_design(design):
    """Return ``design`` with each object where a reference belongs converted when it carries one.

    What cannot be converted moves to ``unreadable`` (name -> value), so a stored state loads and
    says what it could not read.
    """
    document = dict(design)
    unreadable = dict(document.get("unreadable") or {})
    convert_fields(document, REFERENCE_FIELDS, unreadable)
    alternatives = []
    for index, item in enumerate(document.get("alternatives") or ()):
        item = dict(item) if isinstance(item, dict) else {"unreadable": item}
        convert_fields(
            item, {"design": "design", "result": "result"}, unreadable, f"alternatives/{index}/"
        )
        alternatives.append(item)
    if "alternatives" in document:
        document["alternatives"] = alternatives
    return {**document, **({"unreadable": unreadable} if unreadable else {})}


class ProblemState(Record):
    """The notes of one chat; ``version`` is raised by one with every change.

    NOTE: the state is frozen, so a change is always a new state and the only writer is ``apply`` of
    the engine, over events. ``preferences`` are what the user said about how they work, such as
    the units they read, set from the coordinator's route. ``case_origin`` is ``{case, files}``,
    the case the user or the project
    gave, which ``set_case`` writes and verification compares the case with. NOTE: ``compaction``
    is kept here because ``save_state`` is the only
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
    calculations: tuple[Calculation, ...] = ()
    case: dict[str, Any] | None = None
    case_origin: dict[str, Any] | None = None
    preferences: dict[str, Any] = {}
    compaction: Compaction | None = None

    @field_validator("design", mode="before")
    @classmethod
    def _typed_design(cls, design, info):
        """Validate the design section as ``DesignState``.

        Update_state's validation (``context={"strict": True}``) refuses an object where a
        reference belongs and says the shape; loading a stored state converts or sets it aside.
        """
        if not isinstance(design, dict):
            return design
        if not (info.context or {}).get("strict"):
            design = old_design(design)
        DesignState.model_validate(design)
        return design

    @property
    def design_state(self):
        """Return the design section as a typed ``DesignState``."""
        return DesignState.model_validate(self.design)

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
        return ProblemState.model_validate(document, context={"strict": True})
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
    name = item.case_requirement
    linked = f" (case requirement {name})" if name is not None else ""
    return f"Requirement {item.id} [{item.status}]: {item.text}{linked}"


def _assumption_line(item):
    """Return one assumption as a line."""
    status = "confirmed" if item.confirmed else "unconfirmed"
    value = f" = {json.dumps(item.value)}" if item.value is not None else ""
    reason = f", because {item.reason}" if item.reason else ""
    cited = f"; source: {json.dumps(item.citation)}" if item.citation else ""
    return f"Assumption {item.id} [{status}, {item.source}]: {item.text}{value}{reason}{cited}"


def _result_line(item):
    """Return one result as a line."""
    reference = f" ({item.reference})" if item.reference else ""
    return f"Result {item.id}: {item.summary}{reference}"


def _served_files(demand):
    """Return ``service file`` for each service of a demand section that has a power series."""
    served = []
    for name in ("heating", "cooling"):
        power = (demand.get(name) or {}).get("power")
        if isinstance(power, dict) and "file" in power:
            served.append(f"{name} in {power['file']}")
    return served


def _case_line(case):
    """Return the case as one line: its time and its sections, never the demand itself."""
    time = case.get("time") or {}
    span = f"{time.get('start')} to {time.get('end')}"
    sections = ", ".join(name for name in case if name not in ("time", "format", "kind", "name"))
    served = _served_files(case.get("demand") or {})
    line = f"Case: time {span}; sections {sections or 'none'}"
    return f"{line}; demand {', '.join(served)}" if served else line


def render(state):
    """Return compact text, one line per item, or ``""`` for an untouched state.

    The user's preferences show even before the first change, so every agent follows them.
    """
    if state.version == 0 and not state.preferences:
        return ""
    lines = [f"Problem state, version {state.version}"]
    if state.preferences:
        lines.append(f"User preferences: {json.dumps(state.preferences)}")
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
    lines += [
        f"Calculation {item.id}: {item.label} = {json.dumps(item.value)} {item.unit} "
        f"({item.expression})"
        for item in state.calculations
    ]
    if state.case is not None:
        lines.append(_case_line(state.case))
    return "\n".join(lines)
