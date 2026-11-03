"""The case of a run in gemini's terms: the tools that set, read and extend it.

The problem state holds the case as given, the content of a ``case.json`` and the changes of the
model, validated by ``gm.Case.from_dict`` and ``Case.check`` and never written back from
``Case.to_dict``. The files the case names (series such as ``data/demand.csv`` and its
``economics.json``) are run artifacts ``case/<file name>``, so the run store is the source of truth
and a run does not depend on a project folder.

``case_origin`` in the state is the case the user or the project gave, ``{case, files}`` with the
files as ``{name: sha256}``, each kept by its content as ``<sha256>.file``. Verification fails a
design whose case differs from it (``case_changes``) until the user approves the change
(``accept_case``, which only the design loop's driver holds), so no agent passes by weakening the
case.
"""

import copy
import difflib
import hashlib
import io
import json
import re
from typing import Any, Literal

from geomind import runtime
from geomind.errors import ToolError
from geomind.stores.casefiles import case_files, is_safe_name, named_files
from geomind.tools.base import tool
from geomind.tools.files import file_names_schema, project_file
from geomind.tools.gemini.explain import MISSING_CODES, shown_message, unit_error, unit_retry
from geomind.tools.gemini.skeleton import case_skeleton, requirement_shape
from geomind.utils.strings import did_you_mean, join_names

CASE_FILE = "case/"
SERVICES = ("heating", "cooling")
TIME_COLUMN = "time"
TIME_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
PROFILE_NAME = re.compile(r"[A-Za-z0-9_-]+")
SOURCES = ("project", "origin")
OWN_ARGUMENTS = {
    "requirements": "{name: requirement or null} to add, replace or remove one by name",
    "economics": "a merge patch on the content of economics.json",
}
ECONOMICS_FILE = "economics.json"
FILE = ".file"


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


def checked_name(name):
    """Return a file name of a case, which must be a relative path inside the case's folder."""
    if not is_safe_name(name):
        raise ToolError(
            f"case: file = {name!r}; expected a relative path such as 'data/demand.csv', not "
            "absolute and without '..'",
            path="file",
        )
    return name


def state_case(context):
    """Return a copy of the state's case dict, or raise what the model must do."""
    data = context.problem.case
    if data is None:
        raise ToolError(
            "case: the problem state has no case; expected one. Call set_case (source='project' "
            "for the project's case, or changes with the values) or ask_user for them",
            code="no_case",
        )
    return copy.deepcopy(data)


def file_contents(context, data, supplied):
    """Return ``{name: bytes}`` of the files ``data`` names: ``supplied``, else the run's own."""
    for name in case_files(data):
        checked_name(name)

    def read(name):
        if name in supplied:
            return supplied[name]
        return context.session.load_artifact(f"{CASE_FILE}{name}")

    return named_files(data, read)


def digests(files):
    """Return ``{file name: sha256}`` of ``{file name: bytes}``."""
    return {name: hashlib.sha256(content).hexdigest() for name, content in files.items()}


async def keep_files(context, files):
    """Keep each file once by its content, as ``<sha256>.file``."""
    for content in files.values():
        await context.session.save_artifact(f"{hashlib.sha256(content).hexdigest()}{FILE}", content)


def kept_files(context, named):
    """Return ``{file name: bytes}`` of ``{file name: sha256}`` that ``keep_files`` kept."""
    load = context.session.load_artifact
    return {name: load(f"{digest}{FILE}") for name, digest in named.items()}


def build_case(data, files):
    """Return the ``gm.Case`` of a case dict and the bytes of the files it names."""
    import gemini as gm

    return gm.Case.from_dict(copy.deepcopy(data), files=files)


HEADER = {"format", "kind", "name"}
TIME_COLUMN = "time"
"""The column gemini reads a series' times from."""


def readable_case(data, files):
    """Return the ``gm.Case`` of a case dict; missing values raise ``case_incomplete``.

    The error keeps gemini's message, and ``suggestions`` lists every missing path; a missing
    header adds the skeleton of a case from gemini's schema, as JSON.
    """
    import gemini as gm

    try:
        return build_case(data, files)
    except gm.errors.ValidationError as error:
        missing = [issue.problem()["path"] for issue in gm.case.missing(data)]
        if not missing:
            raise
        header = HEADER & set(missing)
        shown = shown_paths(missing)
        if error.code not in MISSING_CODES and not header:
            also = [f"case_incomplete: also missing {join_names(shown[0])}"] if shown[0] else []
            unit = unit_retry(error, data) if error.code == "invalid_unit" else []
            raise ToolError(
                shown_message(error),
                code=error.code,
                path=error.path,
                suggestions=[*unit, *also, *shown[1]],
            ) from error
        skeleton = [json.dumps(case_skeleton())] if header else []
        first = (shown[0] or missing)[0]
        raise ToolError(
            shown_message(error),
            code="case_incomplete",
            path=first,
            suggestions=[*shown[0], *shown[1], *skeleton],
        ) from error


def shown_paths(missing):
    """Return ``(paths, shapes)``: the missing paths, a requirement's as one shape of the schema.

    The fields a requirement of another shape lacks, ``requirements[i].on`` for each ``i``, are
    one suggestion: the shape of a requirement from gemini's schema.
    """
    paths = [path for path in missing if not path.startswith("requirements[")]
    return paths, [requirement_shape()] if len(paths) < len(missing) else []


def changes_schema():
    """Return the JSON Schema of ``changes``, with the skeleton of a new case in its description."""
    skeleton = json.dumps(case_skeleton())
    return {
        "anyOf": [{"type": "object"}, {"type": "null"}],
        "default": None,
        "description": f"A JSON merge patch on the case. A new case needs at least {skeleton}.",
    }


def columns_schema():
    """Return the JSON Schema of ``columns``: per file, the header names to rename."""
    renames = {"type": "object", "additionalProperties": {"type": "string"}}
    return {
        "anyOf": [{"type": "object", "additionalProperties": renames}, {"type": "null"}],
        "default": None,
        "description": (
            "Per project file, header names to rename, e.g. {'demand.csv': {'date': 'time'}}."
        ),
    }


def renamed_header(content, renames):
    """Return a CSV's bytes with the names of its header row renamed, the rows untouched."""
    text = content.decode("utf-8-sig")
    header, newline, rest = text.partition("\n")
    ending = "\r" if header.endswith("\r") else ""
    names = [renames.get(name.strip(), name.strip()) for name in header.rstrip("\r").split(",")]
    return (",".join(names) + ending + newline + rest).encode()


def first_columns(supplied, names):
    """Return ``{file: first column}`` of the CSV files ``names`` whose first is not ``time``."""
    found = {}
    for name in names:
        first = supplied[name].decode("utf-8-sig").partition("\n")[0].split(",")[0].strip()
        if first != TIME_COLUMN:
            found[name] = first
    return found


def column_retry(error, supplied, names, changes):
    """Return the ``set_case`` call that renames a file's time column, or ``None``."""
    if "first column" not in str(error) or not names:
        return None
    renames = {name: {first: TIME_COLUMN} for name, first in first_columns(supplied, names).items()}
    if not renames:
        return None
    shown = "<the same changes>" if changes else "None"
    return f"set_case(files={list(names)!r}, columns={renames!r}, changes={shown})"


def checked_case(data, files):
    """Return the ``gm.Case`` of a case dict, or raise gemini's error for its first problem.

    ``Case.from_dict`` raises on what it cannot read; ``Case.check`` finds the rest.
    """
    import gemini as gm

    case = readable_case(data, files)
    issues = case.check()
    if issues:
        first = issues[0].problem()
        raise gm.errors.ValidationError(
            first["message"],
            path=first["path"],
            code=first["code"],
            suggestions=first["suggestions"],
            problems=[issue.problem() for issue in issues],
        )
    return case


def case_of(context):
    """Return the state's case as a ``gm.Case``; without a case, raise a ``ToolError``.

    There is no fallback case: the model sets one with ``set_case`` or asks the user.
    """
    data = state_case(context)
    return readable_case(data, file_contents(context, data, {}))


async def store_case(context, data, supplied, origin=None):
    """Validate a case dict with its files, keep the files and the case; return the version.

    ``origin`` is ``(case dict, files)`` of the case the user or the project gave, kept as the
    state's ``case_origin``; ``None`` leaves the origin as it is. A rejected case stores nothing.
    """
    files = await runtime.in_gemini_thread(file_contents, context, data, supplied)
    checked_case(data, files)
    for name in supplied.keys() & files.keys():
        await context.session.save_artifact(f"{CASE_FILE}{name}", supplied[name])
    changes = [{"op": "replace", "path": "/case", "value": data}]
    if origin is not None:
        await keep_files(context, origin[1])
        value = {"case": origin[0], "files": digests(origin[1])}
        changes.append({"op": "add", "path": "/case_origin", "value": value})
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
    data, files = found
    for name in map(checked_name, case_files(data)):
        if name not in files:
            raise ToolError(
                f"set_case: the project's case names the file {name!r}, which the project does "
                "not have; expected the file beside its case.json, or ask_user for it",
                code="unknown_name",
                path="source",
            )
    return copy.deepcopy(data), dict(files)


def origin_case(context):
    """Return ``(case dict, {name: bytes})`` of the state's ``case_origin``, or raise."""
    origin = context.problem.case_origin
    if origin is None:
        raise ToolError(
            "set_case: the problem state has no case the user or the project gave; expected "
            "source='project' or changes",
            code="unknown_name",
            path="source",
        )
    return copy.deepcopy(origin["case"]), kept_files(context, origin["files"])


def base_case(context, source):
    """Return ``(case dict, supplied files)`` that ``set_case`` changes."""
    if source is None:
        return (state_case(context) if context.problem.case is not None else {}), {}
    if source == "project":
        return project_case(context)
    if source == "origin":
        return origin_case(context)
    raise ToolError(
        f"set_case: source = {source!r}; expected {join_names(SOURCES)} or none",
        path="source",
    )


def unpassed_files(changes, files):
    """Return ``files`` with the files a series of ``changes`` names that ``files`` lacks."""
    passed = list(files or [])
    return passed + sorted(set(case_files(changes)) - set(passed))


def by_name(requirements):
    """Return a requirement list as ``{name: requirement}``, the form of the argument."""
    if not isinstance(requirements, list):
        return requirements
    return {
        item.get("name"): {key: value for key, value in item.items() if key != "name"}
        for item in requirements
        if isinstance(item, dict)
    }


def own_argument_retry(changes, key, files):
    """Return the ``set_case`` call that moves ``key`` out of ``changes`` to its own argument."""
    value = by_name(changes[key]) if key == "requirements" else changes[key]
    retry = f"set_case(changes=<the same changes without {key!r}>, {key}={value!r}"
    needed = unpassed_files(changes, files)
    return retry + (f", files={needed!r})" if needed != list(files or []) else ")")


def checked_changes(changes, files):
    """Return ``changes`` if it leaves ``requirements`` and ``economics`` to their own argument.

    The error's suggestion is the call that moves it, with ``files`` naming every file a series
    of the changes needs.
    """
    for key, form in OWN_ARGUMENTS.items():
        if key in changes:
            raise ToolError(
                f"set_case: changes has {key!r}; expected the argument {key!r}: {form}",
                path=f"changes.{key}",
                suggestions=[own_argument_retry(changes, key, files)],
            )
    return changes


def case_retries(error, data, supplied, files, columns, changes):
    """Return the next calls a rejected case suggests: renamed columns, files, a unit."""
    retries = [column_retry(error, supplied, files or [], changes)]
    needed = unpassed_files(changes or {}, files)
    if needed != list(files or []) and not set(needed) <= supplied.keys():
        shown = f", columns={columns!r}" if columns else ""
        retries.append(
            f"set_case(files={needed!r}{shown}, changes=<the same changes>, and the same "
            "requirements and economics): a rejected call stored nothing, so send the files "
            "together with everything else of this call"
        )
    if error.code == "invalid_unit":
        retries.extend(unit_retry(error, data))
    retries.append(zone_retry(error, files, columns))
    retries.extend(renamed_columns(error, data, columns))
    return [retry for retry in retries if retry is not None]


def renamed_columns(error, data, columns):
    """Return the column a series names by the name ``columns`` gave it, for each one renamed."""
    from geomind.tools.gemini.explain import field_of

    problems = getattr(error, "problems", None) or [error.to_dict()]
    retries = []
    for problem in problems:
        path = problem.get("path") or ""
        if not path.endswith(".column"):
            continue
        named = field_of(data, path)
        for file, renames in (columns or {}).items():
            if named in renames:
                new = renames[named]
                retries.append(
                    f"{path} = {new!r}: columns renamed {named!r} to {new!r} in {file}, so the "
                    f"series names the new header"
                )
    return retries


NO_OFFSET = "has no offset"
"""How gemini says a series time lacks its UTC offset."""
ZONE = "<IANA zone of time.start>"
"""The placeholder of a series' ``time_zone``: the model chooses it, geomind has no zone."""


def zone_retry(error, files, columns):
    """Return the ``set_case`` call that gives ``time_zone`` to each series whose times lack one.

    gemini reads a time without an offset as local time in the series' ``time_zone`` (an IANA
    name); the zone is the one ``time.start`` is meant in, chosen by the model and recorded as an
    assumption with a reason.
    """
    paths = {
        problem["path"].removesuffix(".file")
        for problem in getattr(error, "problems", None) or ()
        if isinstance(problem, dict) and NO_OFFSET in problem.get("message", "")
    }
    if not paths:
        return None
    patch = {}
    for path in sorted(paths):
        node = patch
        for part in path.split("."):
            node = node.setdefault(part, {})
        node["time_zone"] = ZONE
    passed = f", files={list(files)!r}" if files else ""
    passed += f", columns={columns!r}" if columns else ""
    return (
        f"set_case(changes=<the same changes merged with {patch!r}>{passed}); record the zone "
        "as an assumption with its reason"
    )


def edited_requirements(current, edits):
    """Return the requirement list with ``edits`` ``{name: dict | None}`` applied by name."""
    items = copy.deepcopy(current or [])
    names = [item.get("name") for item in items]
    for name, value in edits.items():
        if value is not None and not isinstance(value, dict):
            raise ToolError(
                f"set_case: requirements.{name} = {value!r}; expected a requirement object or null",
                path=f"requirements.{name}",
            )
        if value is None and name not in names:
            raise ToolError(
                f"set_case: requirements.{name}; expected a requirement the case has: "
                f"{join_names(names)}{did_you_mean(name, names)}",
                code="unknown_name",
                path=f"requirements.{name}",
            )
        if value is None:
            items = [item for item in items if item.get("name") != name]
        elif name in names:
            items[names.index(name)] = {**value, "name": name}
        else:
            items.append({**value, "name": name})
        names = [item.get("name") for item in items]
    return items


def edited_economics(context, data, supplied, patch):
    """Set the economics of ``data`` by a merge ``patch``; return the files with the new content.

    The economics file is stored whole as a new content, under the name the case gives it (or
    ``economics.json`` for a case that has none); an economics written inline is patched in place.
    """
    named = data.get("economics")
    if isinstance(named, dict):
        data["economics"] = merge_patch(named, patch)
        return supplied
    name = checked_name(named or ECONOMICS_FILE)
    data["economics"] = name
    current = file_contents(context, data, supplied).get(name)
    content = json.loads(current) if current is not None else {}
    text = json.dumps(merge_patch(content, patch), indent=2, ensure_ascii=False)
    return {**supplied, name: text.encode()}


def project_files_of(context, names, columns=None):
    """Return ``{name: bytes}`` of the project files ``set_case`` gives to the case.

    ``columns`` renames header names of a file first, so a time column gemini reads as ``time``.
    """
    found = {checked_name(name): project_file(context, "set_case", name) for name in names}
    for name, renames in (columns or {}).items():
        if name in found:
            found[name] = renamed_header(found[name], renames)
    return found


@tool(
    effect="write",
    idempotent=False,
    reruns_in_replay=True,
    late_schemas={"files": file_names_schema, "changes": changes_schema, "columns": columns_schema},
)
async def set_case(
    context,
    source: str | None = None,
    changes: dict[str, Any] | None = None,
    requirements: dict[str, dict[str, Any] | None] | None = None,
    economics: dict[str, Any] | None = None,
    files: list[str] | None = None,
    columns: dict[str, dict[str, str]] | None = None,
):
    """Set the case of the problem state: the project's case, changes to it, or both.

    ``source`` is ``project`` to load the project's ``case.json`` and its files, ``origin`` to go
    back to the case the user or the project gave, or omitted to start from the state's case (an
    empty one when it has none). ``changes`` is a JSON merge patch (RFC 7386) on the case: an
    object merges into the case, a value replaces, null removes a key; it never holds
    ``requirements`` or ``economics``. ``requirements`` is ``{name: requirement or null}``: a
    requirement object adds or replaces the one of that name, null removes it, and the others stay.
    ``economics`` is a merge patch on the content of the case's economics file. ``files`` names
    project files (``list_files``): their bytes go to gemini, under the same name, so a data file
    is given to the case and never retyped: name it in ``changes``, as the ``file`` of a series.
    ``columns`` renames header names of those files, such as ``{"demand.csv": {"date": "time"}}``:
    gemini reads a series' times from a column named ``time``. Once a case is stored, send only
    the keys that change: ``changes`` merges into it, and a rejected call stores nothing. The
    sections are
    in ``read_case(section="schema")``, the exact schema. gemini validates the result: a rejected
    case comes back with the path and message to fix, and nothing is stored; a case with values
    missing is ``case_incomplete``, every missing path in ``suggestions``. The project's case, or
    the first case of a chat, is the case the user gave; a design is verified only on it, so any
    later change of it, economics included, waits for the user's approval. Returns the case and
    the state version.
    """
    import gemini as gm

    alone = files and source is None and not (changes or requirements or economics)
    if alone and context.problem.case is None:
        raise ToolError(
            f"set_case: files = {files!r} and nothing else; expected the changes that name them "
            "in the same call: files alone set no case, and a rejected call stores nothing",
            code="case_incomplete",
            path="format",
            suggestions=[json.dumps(case_skeleton())],
        )
    base, supplied = base_case(context, source)
    if files:
        given = await runtime.in_gemini_thread(project_files_of, context, files, columns)
        supplied = {**supplied, **given}
    data = merge_patch(base, checked_changes(changes or {}, files))
    if requirements:
        data["requirements"] = edited_requirements(data.get("requirements"), requirements)
    contents = edited_economics(context, data, supplied, economics) if economics else supplied
    origin = given_case(context, source, (base, supplied), (data, contents))
    try:
        version = await store_case(context, data, contents, origin)
    except gm.errors.ValidationError as error:
        retries = case_retries(error, data, supplied, files, columns, changes)
        if not retries:
            raise
        raise ToolError(
            shown_message(error), code=error.code, path=error.path, suggestions=retries
        ) from error
    return {"case": data, "version": version}


def given_case(context, source, base, current):
    """Return ``(case dict, files)`` that ``set_case`` keeps as the origin, or ``None``.

    The project's case is the origin, without the changes of the same call; the first case of a
    chat is the origin as it is set, since it comes from the user's request or answer.
    """
    if source == "project":
        return base[0], file_contents(context, base[0], base[1])
    if source is None and context.problem.case_origin is None:
        return current[0], file_contents(context, *current)
    return None


def economics_of(context, data):
    """Return the parsed economics of a case dict: its file's content, or the inline object."""
    named = data.get("economics")
    if isinstance(named, dict):
        return named
    content = file_contents(context, data, {}).get(named) if named else None
    if content is None:
        raise ToolError(
            "read_case: the case has no economics file in the run; expected set_case with the "
            "economics",
            code="unknown_name",
            path="section",
        )
    return json.loads(content)


@tool(effect="read", keeps_result="run")
def describe_case(path: str):
    """Say what each key of the case or its economics under ``path`` means, with its units.

    ``path`` is a dotted key or a part of one, such as ``site.air``, ``demand.cooling``,
    ``requirements`` (also what each option means) or ``economics.capex``. Returns ``keys``, one
    line each: the key, its form and units, its meaning and where its value comes from.
    """
    from geomind.tools.gemini.skeleton import keys_under

    lines = keys_under(path)
    if lines:
        return {"keys": lines}
    parts = ["format", "kind", "name", "time", "site", "demand", "utilities", "requirements"]
    parts += ["economics"]
    raise ToolError(
        f"describe_case: path = {path!r}; expected a key or a part of one, such as "
        f"{', '.join(parts)}",
        code="unknown_name",
        path="path",
        suggestions=difflib.get_close_matches(path.split(".")[0], parts),
    )


@tool(effect="read")
def read_case(context, section: str | None = None):
    """Return the case of the problem state, one of its sections, its economics or the schema.

    ``section`` is a key of the case (``time``, ``site``, ``demand``, ``utilities``,
    ``requirements``, ``initial_state``), ``economics`` for the content of the economics file, or
    ``schema`` for the JSON Schema of a case (and of the economics under ``economics_schema``).
    """
    import gemini as gm

    if section == "schema":
        return {**gm.Case.schema(), "economics_schema": gm.case.Economics.schema()}
    data = state_case(context)
    if section is None:
        return data
    if section == "economics":
        return economics_of(context, data)
    if section not in data:
        names = sorted(gm.Case.schema()["properties"])
        raise ToolError(
            f"read_case: section = {section!r}; expected one of {join_names(names)} or 'schema'"
            f"{did_you_mean(section, names)}, and one the case has: {join_names(sorted(data))}",
            path="section",
        )
    return data[section]


def profile_csv(frame, name, values):
    """Return the CSV bytes of a profile: the ``time`` column of ``frame`` and the ``values``."""
    import pandas as pd

    table = pd.DataFrame({TIME_COLUMN: frame.index.strftime(TIME_FORMAT), name: list(values)})
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
    try:
        return gm.units.Quantity(step["value"], step["unit"]).to("s").value
    except gm.errors.ValidationError as error:
        raise unit_error(error, "duration") from error


def followed_time(case, frame, step):
    """Return the case's ``time`` made to follow the profile ``frame``, or ``None`` if it covers.

    A profile that starts after the case's start or ends before its end does not cover the case's
    time; the time then becomes the profile's own span and step.
    """
    import pandas as pd

    end = frame.index[-1] + pd.Timedelta(seconds=step_seconds(step))
    if frame.index[0] <= case.time.start and end >= case.time.end:
        return None
    return {
        "start": frame.index[0].strftime(TIME_FORMAT),
        "end": end.strftime(TIME_FORMAT),
        "step": step,
    }


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
    to the run's case files as ``data/<name>.csv`` with a ``time`` column and the column ``name``,
    in ``unit``, and the ``power`` of the service points at it; the rest of the demand is kept. A
    profile that does not cover the case's ``time`` sets the time to the profile's own span and
    step, in the same call. The service's temperatures and the other series must fit the result:
    gemini rejects the case otherwise and nothing is stored.
    """
    import gemini as gm

    check_profile_name(name)
    quantity = f"{service}_demand"
    frame = gm.case.from_values(values, unit, start, step_seconds(step), quantity)
    case = await runtime.in_gemini_thread(case_of, context)
    data = state_case(context)
    file = f"data/{name}.csv"
    demand = data.setdefault("demand", {})
    demand.setdefault(service, {})["power"] = {"unit": unit, "file": file, "column": name}
    time = followed_time(case, frame, step)
    if time is not None:
        data["time"] = time
    version = await store_case(context, data, {file: profile_csv(frame, name, values)})
    shown = {"demand": data["demand"], "time": data["time"]}
    return {**shown, "steps": len(values), "version": version}
