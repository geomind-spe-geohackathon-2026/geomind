"""The tool that writes the problem state."""

import typing
from typing import Any

import pydantic

from geomind.context.state import Assumption, ProblemState, Question, Requirement, Result
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.types.patch import OPERATIONS

CASE_KEYS = ("case", "case_origin")
TOOL_KEYS = {"calculations": "calculate", "findings": "the engine, from each teammate's answer"}
"""State keys only one tool writes, by the tool that writes each."""
ROOTS = ("goal", "requirements", "assumptions", "design", "results", "verification", "questions")
ITEM_MODELS = {
    "requirements": Requirement,
    "assumptions": Assumption,
    "results": Result,
    "questions": Question,
}
PATH_PATTERN = "^/(" + "|".join(ROOTS) + ")(/.*)?$"
PATH_DESCRIPTION = (
    "A JSON Pointer under goal, requirements, assumptions, design, results, verification or "
    "questions. Forms: '/goal'; '/results/-' (add appends an item); '/results/R1' (replace or "
    "remove the item with id R1); '/assumptions/A1/confirmed' (a field of an item by id); "
    "'/design/<key>'. An item is never addressed by position."
)


def value_description():
    """Return what ``value`` holds, with the shape of each list's item, from the state's models."""
    shapes = "; ".join(f"{root} item {shape_of(model)}" for root, model in ITEM_MODELS.items())
    return (
        "Absent on remove. For '/<list>/-' and '/<list>/<id>' one item: "
        f"{shapes}. For '/goal' a string; for a field of an item the field's value."
    )


def changes_schema():
    """Return the JSON Schema of ``changes``: operations with the shape of ``value`` in words.

    NOTE: the models are not sent as ``$defs`` with ``anyOf``: that cost more than the shapes in
    words, and the tool checks the value against the model of the path and returns the shape
    expected there when it does not fit.
    """
    operation = {
        "type": "object",
        "properties": {
            "op": {"enum": list(OPERATIONS)},
            "path": {"type": "string", "pattern": PATH_PATTERN, "description": PATH_DESCRIPTION},
            "value": {"description": value_description()},
        },
        "required": ["op", "path"],
        "additionalProperties": False,
    }
    return {
        "type": "array",
        "items": operation,
        "minItems": 1,
        "description": "JSON Patch operations, applied together or not at all.",
    }


def annotation_text(annotation):
    """Return a field type as JSON-like text: ``string``, ``string | null``, ``user | agent``."""
    names = {str: "string", bool: "boolean", int: "integer", float: "number", type(None): "null"}
    if typing.get_origin(annotation) is typing.Literal:
        return " | ".join(typing.get_args(annotation))
    if typing.get_args(annotation):
        return " | ".join(annotation_text(part) for part in typing.get_args(annotation))
    return names.get(
        annotation, "any" if annotation is Any else getattr(annotation, "__name__", "any")
    )


def shape_of(model):
    """Return the shape of an item as text: each field with its type, a ``?`` after an optional."""
    fields = {
        (name if field.is_required() else f"{name}?"): annotation_text(field.annotation)
        for name, field in model.model_fields.items()
    }
    return str(fields).replace('"', "'")


def refusal(position, change, reason, expected):
    """Return the tool error of a change that does not fit, with the shape expected there."""
    return ToolError(
        f"update_state: changes[{position}] = {change}; {reason}; expected {expected}",
        code="invalid_input",
        path=f"changes[{position}]",
    )


def item_problem(model, value):
    """Return what is wrong with a value as an item of ``model``, or ``None``."""
    if not isinstance(value, dict):
        return f"value = {value!r} is not an object"
    try:
        model.model_validate(value)
    except pydantic.ValidationError as error:
        return "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
    return None


def check_item(position, change, model, root, form):
    """Raise unless the value of ``change`` is one item of ``model``."""
    problem = item_problem(model, change.get("value"))
    if problem is not None:
        raise refusal(
            position, change, problem, f"{form} to hold {model.__name__} {shape_of(model)}"
        )


def check_list(position, change, model, root):
    """Raise unless the value of ``change`` is a list of items of ``model``."""
    value = change.get("value")
    if not isinstance(value, list):
        raise refusal(
            position,
            change,
            f"value is not a list; '/{root}' holds a list",
            f"a list of {model.__name__} {shape_of(model)}, or append one item with '/{root}/-'",
        )
    for item in value:
        check_item(position, {**change, "value": item}, model, root, f"each item of '/{root}'")


def check_field(position, change, model, tokens):
    """Raise when the field named by ``/<list>/<id>/<field>`` is not one of the model."""
    if tokens[2] in model.model_fields:
        return
    raise refusal(
        position,
        change,
        f"field = {tokens[2]!r} is not a field of {model.__name__}",
        f"one of {shape_of(model)} (the field of an item by id, as /{tokens[0]}/{tokens[1]}/"
        f"{next(iter(model.model_fields))})",
    )


def check_shape(position, change):
    """Raise when the path form or the value of one operation does not fit the state's shape."""
    tokens = str(change.get("path", "")).split("/")[1:]
    if not tokens or change.get("op") == "remove":
        return
    root = tokens[0]
    if root == "goal" and len(tokens) == 1 and not isinstance(change.get("value"), str):
        raise refusal(position, change, f"value = {change.get('value')!r}", "a string for '/goal'")
    model = ITEM_MODELS.get(root)
    if model is None:
        return check_section_path(position, change, tokens)
    check_item_path(position, change, model, tokens)


def annotation_at(tokens):
    """Return the type the state model gives the path ``tokens``, or ``None`` where it is open.

    The shape of a section comes from ``ProblemState`` alone: a typed ``design`` or
    ``verification`` is checked below its root, and an open one (``dict[str, Any]``) is not.
    """
    annotation = ProblemState.model_fields[tokens[0]].annotation
    for token in tokens[1:]:
        if isinstance(annotation, type) and issubclass(annotation, pydantic.BaseModel):
            field = annotation.model_fields.get(token)
            annotation = None if field is None else field.annotation
        elif typing.get_origin(annotation) is dict:
            annotation = typing.get_args(annotation)[1]
        else:
            return None
    return None if annotation is Any else annotation


def check_section_path(position, change, tokens):
    """Raise when a value for a typed key of ``design`` or ``verification`` does not fit."""
    if tokens[0] not in ("design", "verification") or len(tokens) < 2:
        return
    annotation = annotation_at(tokens)
    if annotation is None:
        return
    try:
        pydantic.TypeAdapter(annotation).validate_python(change.get("value"))
    except pydantic.ValidationError as error:
        problems = "; ".join(f"{'.'.join(map(str, e['loc']))}: {e['msg']}" for e in error.errors())
        expected = shape_of(annotation) if hasattr(annotation, "model_fields") else None
        raise refusal(
            position,
            change,
            problems,
            f"'{change['path']}' to hold {expected or annotation_text(annotation)}",
        ) from error


def check_item_path(position, change, model, tokens):
    """Raise when an operation on an id-addressed list has the wrong path form or item shape."""
    root = tokens[0]
    if len(tokens) == 1:
        return check_list(position, change, model, root)
    if len(tokens) == 3:
        return check_field(position, change, model, tokens)
    if len(tokens) > 3:
        return None
    if tokens[1] == "-":
        return check_item(position, change, model, root, f"'/{root}/-'")
    if change.get("op") == "add":
        raise refusal(
            position,
            change,
            f"path = {change['path']!r} is not an append",
            f"'/{root}/-' to add {model.__name__} {shape_of(model)}; items are addressed by id, "
            "never by position or name",
        )
    return check_item(position, change, model, root, f"'/{root}/{tokens[1]}'")


def check_shapes(changes):
    """Raise on the first operation of ``changes`` whose path form or value shape does not fit."""
    for position, change in enumerate(changes):
        if isinstance(change, dict) and change.get("op") in OPERATIONS:
            check_shape(position, change)


def check_no_case(changes):
    """Raise when a change reaches the case, which only set_case writes after gemini checks it."""
    for position, change in enumerate(changes):
        path = change.get("path") if isinstance(change, dict) else None
        key = path.split("/")[1] if isinstance(path, str) and path.count("/") >= 1 else None
        if key in CASE_KEYS:
            raise ToolError(
                f"update_state: changes[{position}].path = {path!r}; the case is written only by "
                "set_case, which gemini validates",
                code="not_allowed",
                path=f"changes[{position}].path",
            )
        if key in TOOL_KEYS:
            raise ToolError(
                f"update_state: changes[{position}].path = {path!r}; {key} are written only by "
                f"{TOOL_KEYS[key]}, which keeps the source of every operand",
                code="not_allowed",
                path=f"changes[{position}].path",
            )


@tool(
    effect="write",
    idempotent=False,
    reruns_in_replay=True,
    late_schemas={"changes": changes_schema},
)
async def update_state(context, changes: list[dict[str, Any]]):
    """Change the problem state with JSON Patch operations (add, replace, remove).

    Skill `working-in-a-team`.
    """
    check_no_case(changes)
    check_shapes(changes)
    return {"version": await context.session.change_state(changes)}
