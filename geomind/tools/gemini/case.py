"""The case of a run in gemini's terms: the tools that set, read and extend it.

The problem state holds the case as given, the content of a ``case.json`` and the changes of the
model, validated by ``gm.Case.from_dict`` and never written back from ``Case.to_dict`` (which does
not round-trip the demand). The files the case names are run artifacts ``case/<file name>``, so
the run store is the source of truth and a run does not depend on a project folder.
"""

import copy
import io
import re
import tempfile
from pathlib import Path
from typing import Any, Literal

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.utils.strings import did_you_mean, join_names

CASE_FILE = "case/"
SERVICES = ("heating", "cooling")
TIME_COLUMN = "time"
PROFILE_NAME = re.compile(r"[A-Za-z0-9_-]+")
SOURCES = ("project",)


def merge_patch(target, patch):
    """Return ``target`` with the RFC 7386 JSON merge patch applied; ``target`` stays as it was."""
    if not isinstance(patch, dict):
        return copy.deepcopy(patch)
    result = dict(target) if isinstance(target, dict) else {}
    for key, value in patch.items():
        if value is None:
            result.pop(key, None)
            continue
        result[key] = merge_patch(result.get(key), value)
    return result


def case_files(node):
    """Return the names of the files a case dict names: every ``file`` of a section or profile."""
    if isinstance(node, list):
        return [name for item in node for name in case_files(item)]
    if not isinstance(node, dict):
        return []
    named = [node["file"]] if isinstance(node.get("file"), str) else []
    return named + [name for item in node.values() for name in case_files(item)]


def checked_name(name):
    """Return a file name of a case, which must be one name and no path."""
    if not name or Path(name).name != name or name in (".", ".."):
        raise ToolError(
            f"case: file = {name!r}; expected a file name without a folder", path="demand.file"
        )
    return name


def state_case(context):
    """Return a copy of the state's case dict, or raise what the model must do."""
    data = context.problem.case
    if data is None:
        raise ToolError(
            "case: the problem state has no case; expected one. Call set_case (source='project' "
            "for the project's case, or changes with the values) or ask_user for them"
        )
    return copy.deepcopy(data)


def file_contents(context, data, supplied):
    """Return ``{name: bytes}`` of the files ``data`` names: ``supplied``, else the run's own."""
    files = {}
    for name in map(checked_name, case_files(data)):
        content = supplied.get(name) or context.session.load_artifact(f"{CASE_FILE}{name}")
        if content is not None:
            files[name] = content
    return files


def build_case(data, files):
    """Return the ``gm.Case`` of a case dict, its files written to a folder for gemini to read."""
    import gemini as gm

    with tempfile.TemporaryDirectory() as folder:
        for name, content in files.items():
            (Path(folder) / name).write_bytes(content)
        return gm.Case.from_dict(copy.deepcopy(data), folder)


def case_of(context):
    """Return the state's case as a ``gm.Case``; without a case, raise a ``ToolError``.

    There is no fallback case: the model sets one with ``set_case`` or asks the user.
    """
    data = state_case(context)
    return build_case(data, file_contents(context, data, {}))


async def store_case(context, data, supplied):
    """Validate a case dict with its files, keep the files and the case; return the version."""
    files = file_contents(context, data, supplied)
    build_case(data, files)
    for name in supplied.keys() & files.keys():
        await context.session.save_artifact(f"{CASE_FILE}{name}", supplied[name])
    changes = [{"op": "replace", "path": "/case", "value": data}]
    return await context.session.change_state(changes)


def project_case(context):
    """Return ``(case dict, {name: bytes})`` of the run's project, or raise a result to act on."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError(
            "set_case: this run has no project; expected a workspace and one",
            code="not_allowed",
            path="source",
        )
    found = workspace.case(context.project)
    if found is None:
        raise ToolError(
            f"set_case: project {context.project!r} has no case; expected changes with the values"
            " or ask_user",
            code="unknown_name",
            path="source",
        )
    data, folder = found
    names = map(checked_name, case_files(data))
    files = {name: (Path(folder) / name).read_bytes() for name in names}
    return copy.deepcopy(data), files


def base_case(context, source):
    """Return ``(case dict, supplied files)`` that ``set_case`` changes."""
    if source is None:
        return (state_case(context) if context.problem.case is not None else {}), {}
    if source == "project":
        return project_case(context)
    raise ToolError(
        f"set_case: source = {source!r}; expected {join_names(SOURCES)} or none",
        path="source",
    )


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def set_case(context, source: str | None = None, changes: dict[str, Any] | None = None):
    """Set the case of the problem state: the project's case, changes to it, or both.

    ``source`` is ``project`` to load the project's ``case.json`` and its files, or omitted to
    start from the state's case (an empty one when it has none). ``changes`` is a JSON merge patch
    (RFC 7386) on the case: an object merges into the case, a value replaces, null removes a key.
    The sections are ``time``, ``environment``, ``demand``, ``choices``, ``constraints``,
    ``assumptions`` and ``uncertainty``; ``read_case(section="schema")`` is the exact schema.
    gemini validates the result: a rejected case comes back with the path and message to fix, and
    nothing is stored. Returns the case and the state version.
    """
    data, supplied = base_case(context, source)
    data = merge_patch(data, changes or {})
    version = await store_case(context, data, supplied)
    return {"case": data, "version": version}


@tool(effect="read")
def read_case(context, section: str | None = None):
    """Return the case of the problem state, one of its sections, or gemini's case schema.

    ``section`` is ``time``, ``environment``, ``demand``, ``choices``, ``constraints``,
    ``assumptions``, ``uncertainty``, or ``schema`` for the JSON Schema of a case.
    """
    import gemini as gm

    if section == "schema":
        return gm.Case.schema()
    data = state_case(context)
    if section is None:
        return data
    if section not in data:
        names = sorted(gm.Case.schema()["properties"])
        raise ToolError(
            f"read_case: section = {section!r}; expected one of {join_names(names)} or 'schema'"
            f"{did_you_mean(section, names)}, and one the case has: {join_names(sorted(data))}",
            path="section",
        )
    return data[section]


def other_columns(case, service, frame):
    """Return ``{service: (column, values in W)}`` of the other services of ``case``."""
    others = {}
    if case.demand is None:
        return others
    for name in SERVICES:
        given = getattr(case.demand, name)
        if name != service and given is not None:
            if not case.demand.frame.index.equals(frame.index):
                raise ToolError(
                    f"save_profile: the case's {name} demand is on other steps than the profile; "
                    f"expected the same steps, or remove it with set_case changes "
                    f"{{'demand': {{'{name}': null}}}}",
                    path="start",
                )
            others[name] = (given.column, case.demand.frame[f"{name}_demand"])
    return others


def profile_csv(frame, name, values, others):
    """Return the CSV text of the new column, the time and the columns of the other services."""
    import pandas as pd

    table = pd.DataFrame({TIME_COLUMN: [moment.isoformat() for moment in frame.index]})
    table[name] = list(values)
    for column, series in others.values():
        table[column] = series.to_numpy()
    buffer = io.StringIO()
    table.to_csv(buffer, index=False)
    return buffer.getvalue().encode()


def check_profile_name(name):
    """Raise unless ``name`` can be a column and a file name."""
    if not PROFILE_NAME.fullmatch(name) or name == TIME_COLUMN:
        raise ToolError(
            f"save_profile: name = {name!r}; expected letters, digits, '_' or '-', and not "
            f"{TIME_COLUMN!r}",
            path="name",
        )


def step_seconds(step):
    """Return the seconds of a step ``{value, unit}``, through ``gm.units.Quantity``."""
    import gemini as gm

    if not isinstance(step, dict) or set(step) != {"value", "unit"}:
        raise ToolError(
            f"save_profile: step = {step!r}; expected {{'value': 1, 'unit': 'd'}}", path="step"
        )
    return gm.units.Quantity(step["value"], step["unit"]).to("s").value


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def save_profile(
    context,
    name: str,
    values: list[float],
    unit: str,
    start: str,
    step: dict[str, Any],
    service: Literal["heating", "cooling"],
):
    """Add a demand profile the user gave as values to the case's demand, and return the demand.

    ``values`` are the demand of the ``service`` (heating or cooling), one per step in the power
    unit ``unit`` (such as ``MW``), from the ISO 8601 time ``start`` at a constant ``step``, given
    as ``{"value": 1, "unit": "d"}``. gemini checks them (finite, not negative). They are written
    to the run's case files as the column ``name`` of ``<name>.csv``, in ``unit``, and the case's
    ``demand`` points at it; the temperatures of the service and its other service are kept. The
    steps must be those of the case's ``time``: set that first with set_case.
    """
    import gemini as gm

    check_profile_name(name)
    quantity = f"{service}_demand"
    frame = gm.data.from_values(values, unit, start, step_seconds(step), quantity)
    case = case_of(context)
    others = other_columns(case, service, frame)
    file = f"{name}.csv"
    demand = {"file": file, "time_column": TIME_COLUMN, service: {"column": name, "unit": unit}}
    demand.update({other: {"column": column, "unit": "W"} for other, (column, _) in others.items()})
    data = merge_patch(state_case(context), {"demand": demand})
    supplied = {file: profile_csv(frame, name, values, others)}
    version = await store_case(context, data, supplied)
    return {"demand": data["demand"], "steps": len(values), "version": version}
