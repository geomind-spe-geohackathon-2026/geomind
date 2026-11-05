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

import contextvars
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
from geomind.tools.files import file_names_schema, has_files, project_file, project_file_names
from geomind.tools.gemini.air import pressure_from_elevation
from geomind.tools.gemini.explain import MISSING_CODES, shown_message, unit_error, unit_retry
from geomind.tools.gemini.skeleton import case_skeleton, requirement_shape
from geomind.tools.gemini.unit_bridge import bridged_requirements, bridged_units
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


def replaced_uncertainties(target, patch):
    """Return ``patch`` with each ``uncertainty`` whose ``kind`` changes set whole (QA-154).

    A merge patch keeps the keys it does not name, so a ``uniform`` over a ``normal`` kept its
    ``std`` and gemini refused it. An uncertainty of another kind is a new one: every key of the
    old kind the patch does not set is removed (``null``).
    """
    if not isinstance(patch, dict) or not isinstance(target, dict):
        return patch
    result = {}
    for key, value in patch.items():
        old = target.get(key)
        if (
            key == "uncertainty"
            and isinstance(value, dict)
            and isinstance(old, dict)
            and value.get("kind") is not None
            and value.get("kind") != old.get("kind")
        ):
            result[key] = {**{name: None for name in old}, **value}
        else:
            result[key] = replaced_uncertainties(old, value)
    return result


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
        if project_has_case(context):
            raise ToolError(
                "case: the problem state has no case yet, but the project has a case file: "
                "set_case(source='project') loads it",
                code="no_case",
            )
        raise ToolError(
            "case: the problem state has no case; expected one. Call set_case (source='project' "
            "for the project's case, or changes with the values) or ask_user for them",
            code="no_case",
        )
    return copy.deepcopy(data)


def project_has_case(context):
    """Return whether the run's project has a case file, so ``no_case`` can say to load it."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        return False
    try:
        return workspace.case(context.project) is not None or bool(case_file_names(context))
    except (OSError, ValueError):
        return False


CASE_JSON = "case.json"
"""The name of a project's case file, beside its data or among the project's files."""


def case_file_names(context):
    """Return the names of the project files that are a ``case.json``, in a folder or not."""
    names = project_file_names(context)
    return [name for name in names if name == CASE_JSON or name.endswith(f"/{CASE_JSON}")]


def files_case(context):
    """Return ``(case dict, {name: bytes})`` of a ``case.json`` among the project files, or none.

    The backend's project keeps the user's files, ``case.json`` among them (``files/case.json``),
    and the workspace's ``case`` reads only one beside the project's data (E2E-1). The files the
    case names are read beside it, in its folder.
    """
    found = case_file_names(context)
    if not found:
        return None
    if len(found) > 1:
        raise ToolError(
            f"set_case: the project has {len(found)} case files, {join_names(found)}; expected "
            "one: ask_user which is the case, then set_case with its values in changes",
            code="invalid_input",
            path="source",
        )
    name = found[0]
    try:
        data = json.loads(project_file(context, "set_case", name))
    except ValueError as error:
        raise ToolError(
            f"set_case: {name} is no JSON ({error}); expected a gemini case", path="source"
        ) from error
    kind = data.get("kind") if isinstance(data, dict) else None
    if kind != "case":
        raise ToolError(
            f"set_case: {name} has kind = {kind!r}; expected 'case', a gemini case file",
            code="invalid_input",
            path="source",
        )
    folder = name.removesuffix(CASE_JSON)
    workspace = context.session.workspace
    files = {}
    for file in map(checked_name, case_files(data)):
        content = workspace.file(context.project, f"{folder}{file}")
        if content is not None:
            files[file] = content
    return data, files


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
        columns = column_choices(missing, data, files)
        raise ToolError(
            shown_message(error),
            code="case_incomplete",
            path=first,
            suggestions=[*shown[0], *shown[1], *columns, *skeleton],
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


TIME_NAMES = re.compile(r"(?i)(date|time|day|timestamp)([ _-]?(utc|local))?")
"""Header names of a first column that is a series' times under another name (QA-222)."""


def time_renames(found, columns):
    """Return ``(files, converted)``: each CSV's first column named like a time renamed ``time``.

    QA-222: the case lead dropped ``columns`` from its full call and gemini refused the files'
    ``date`` column. A first column named as a time (``date``, ``timestamp``) that ``columns``
    leaves as it is IS the time column: renaming its header is a slip of form, not a value, so
    set_case renames it and lists it in ``converted``.
    """
    renamed, converted = dict(found), []
    for name, content in found.items():
        if not name.lower().endswith(".csv"):
            continue
        first = content.decode("utf-8-sig").partition("\n")[0].split(",")[0].strip()
        if first == TIME_COLUMN or first in (columns or {}).get(name, {}):
            continue
        if not TIME_NAMES.fullmatch(first):
            continue
        renamed[name] = renamed_header(content, {first: TIME_COLUMN})
        converted.append({
            "path": f"file {name}",
            "from": {"value": first, "unit": None},
            "to": {"value": TIME_COLUMN, "unit": None},
            "reason": f"gemini reads a series' times from its first column named {TIME_COLUMN!r}",
        })
    return renamed, converted


def without_empty_units(node, path=""):
    """Return ``(node, converted)`` with every ``"unit": ""`` left out (QA-222).

    The case lead wrote ``"unit": ""`` on each fraction, which gemini refuses; a key that takes
    no unit is written without one, so an empty unit is no unit.
    """
    if isinstance(node, list):
        pairs = [without_empty_units(item, f"{path}[{index}]") for index, item in enumerate(node)]
        return [item for item, _ in pairs], [entry for _, found in pairs for entry in found]
    if not isinstance(node, dict):
        return node, []
    result, converted = {}, []
    for key, value in node.items():
        here = f"{path}.{key}" if path else str(key)
        if key == "unit" and isinstance(value, str) and not value.strip():
            converted.append({
                "path": here,
                "from": {"value": None, "unit": value},
                "to": {"value": None, "unit": None},
                "reason": "an empty unit is no unit: a key that takes none is written without it",
            })
            continue
        result[key], found = without_empty_units(value, here)
        converted += found
    return result, converted


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
    """Return the ``gm.Case`` of a case dict, or raise gemini's error with every problem.

    ``Case.from_dict`` raises on what it cannot read; ``Case.check`` finds the rest; the bounds of
    a fraction (``fraction_problems``) join either.
    """
    import gemini as gm

    fractions = fraction_problems(data)
    try:
        case = readable_case(data, files)
    except gm.errors.ValidationError as error:
        raise with_problems(error, fractions) from error
    issues = case.check()
    if issues:
        first = issues[0].problem()
        raise gm.errors.ValidationError(
            first["message"],
            path=first["path"],
            code=first["code"],
            suggestions=first["suggestions"],
            problems=[issue.problem() for issue in issues] + fractions,
        )
    raise_fractions(data)
    return case


FRACTION_WORDS = ("efficiency", "fraction", "share")
"""Words of a requirement quantity whose bounds are a fraction 0-1 when it has no unit (#130)."""


def fraction_problems(data):
    """Return the problems of requirements on an efficiency or fraction bounded outside 0-1 (#130).

    gemini reads such a bound with no unit as a fraction, so ``70`` meant as 70 % passes its
    check and fails every design; nemotron wrote ``pump_efficiency`` ``min 70, max 70``. Read
    from the case dict, so they come back with gemini's own problems in one call (E2E-8).
    """
    import gemini as gm

    roles = gm.plants.roles()
    problems = []
    for index, item in enumerate(data.get("requirements") or ()):
        if not isinstance(item, dict) or not isinstance(item.get("quantity"), str):
            continue
        quantity = item["quantity"]
        read = roles.get(item.get("on"), {}).get(quantity, {})
        if read.get("dimension") is not None or item.get("over") == "duration":
            continue
        if not any(word in quantity for word in FRACTION_WORDS):
            continue
        bounds = [item.get(side) for side in ("min", "max")]
        numbers = [value for value in bounds if isinstance(value, int | float)]
        if all(0 <= value <= 1 for value in numbers):
            continue
        problems.append(
            {
                "path": f"requirements[{index}]",
                "code": "out_of_bounds",
                "message": f"requirements[{index}] ({item.get('name')}): {quantity} min = "
                f"{bounds[0]}, max = {bounds[1]}; an efficiency is a fraction 0-1: 0.7, not 70",
                "suggestions": [],
            }
        )
    return problems


def with_problems(error, problems):
    """Return gemini's ``error`` with ``problems`` of geomind's own added, or ``error`` as it is."""
    import gemini as gm

    if not problems:
        return error
    given = list(getattr(error, "problems", None) or [error.to_dict()])
    return gm.errors.ValidationError(
        str(error),
        path=error.path,
        code=error.code,
        suggestions=list(getattr(error, "suggestions", None) or ()),
        problems=given + problems,
    )


def raise_fractions(data):
    """Raise the fraction problems of ``data`` as one gemini error, if it has any."""
    import gemini as gm

    problems = fraction_problems(data)
    if problems:
        first = problems[0]
        raise gm.errors.ValidationError(
            first["message"], path=first["path"], code=first["code"], problems=problems
        )


def case_of(context):
    """Return the state's case as a ``gm.Case``; without a case, raise a ``ToolError``.

    There is no fallback case: the model sets one with ``set_case`` or asks the user.
    """
    data = state_case(context)
    return readable_case(data, file_contents(context, data, {}))


DRY_RUN = contextvars.ContextVar("geomind_case_dry_run", default=False)
"""Set while ``set_case`` only checks its call before an approval: nothing is stored (QA-037)."""


async def store_case(context, data, supplied, origin=None):
    """Validate a case dict with its files, keep the files and the case; return the version.

    ``origin`` is ``(case dict, files)`` of the case the user or the project gave, kept as the
    state's ``case_origin``; ``None`` leaves the origin as it is. A rejected case stores nothing.
    """
    files = await runtime.in_gemini_thread(file_contents, context, data, supplied)
    checked_case(data, files)
    if DRY_RUN.get():
        return context.problem.version
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
    if found is None and has_files(workspace):
        found = files_case(context)
    if found is None:
        raise ToolError(
            f"set_case: project {context.project!r} has no case: no {CASE_JSON} beside its data "
            f"and none among its files (list_files); expected changes with the values the files "
            "and the user give, or ask_user",
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


def moved_arguments(changes, base, arguments):
    """Return ``(changes, argument values)``: the arguments a new case's changes hold, moved out.

    The run (E2E-8) put ``requirements``, ``files`` and ``columns`` inside the changes of a first
    case and spent a call on each refusal. Each is its argument when that argument is not given
    and, for ``requirements`` and ``economics``, the case has none yet: then the merge patch and
    the argument set the same. Any other stays for ``checked_changes`` to refuse.
    """
    if not isinstance(changes, dict):
        return changes, tuple(arguments.values())
    changes, arguments = dict(changes), dict(arguments)
    for key, fits in MOVABLE.items():
        if key not in changes or arguments.get(key) is not None or base.get(key) is not None:
            continue
        if fits(changes[key]):
            value = changes.pop(key)
            arguments[key] = by_name(value) if key == "requirements" else value
    return changes, tuple(arguments.values())


def named_requirements(value):
    """Tell whether ``value`` is a requirement list, each with its name, or one by name."""
    if isinstance(value, dict):
        return all(isinstance(item, dict) for item in value.values())
    return isinstance(value, list) and all(
        isinstance(item, dict) and isinstance(item.get("name"), str) for item in value
    )


MOVABLE = {
    "requirements": named_requirements,
    "economics": lambda value: isinstance(value, dict),
    "files": lambda value: isinstance(value, list) and all(isinstance(n, str) for n in value),
    "columns": lambda value: isinstance(value, dict),
}
"""The arguments of set_case a new case's ``changes`` may hold, with the form each must have."""


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
    paths = [problem.get("path") for problem in getattr(error, "problems", None) or ()]
    retries.extend(column_choices([error.path, *paths], data, supplied))
    return [retry for retry in dict.fromkeys(retries) if retry is not None]


def column_choices(paths, data, files):
    """Return, per series ``path`` that lacks its column, the columns its file has (E2E-8).

    The run: ``demand.heating.power.column = None; expected text`` came with no suggestion, and
    the model guessed. The file's header names but ``time`` are what the column may be.
    """
    from geomind.tools.gemini.explain import field_of

    choices = []
    for path in dict.fromkeys(path for path in paths if path):
        if not path.endswith(".column") or field_of(data, path) is not None:
            continue
        file = field_of(data, path.removesuffix(".column") + ".file")
        content = files.get(file) if isinstance(file, str) else None
        if content is None:
            continue
        header = content.decode("utf-8-sig").partition("\n")[0].rstrip("\r").split(",")
        names = [name.strip() for name in header if name.strip() != TIME_COLUMN]
        shown = ", ".join(repr(name) for name in names)
        choices.append(f"{path}: a column of {file}: {shown}")
    return choices


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


RUNNING_REASON = (
    "a supply temperature is judged while the supply runs: on a step with no demand the loop "
    "carries no flow and its idle temperature is no supply"
)


def running_supply_temperatures(requirements):
    """Return ``converted`` entries after judging supply temperatures only while running.

    A per-step temperature on a heating or cooling supply checked ``always`` (or with no
    ``when``) failed every zero-demand day, where the idle loop sits at its return (QA-091);
    gemini's ``running`` (the module carried flow) is what the brief means. Edits in place.
    """
    converted = []
    for item in requirements if isinstance(requirements, list) else ():
        if not isinstance(item, dict) or item.get("quantity") != "temperature":
            continue
        if not str(item.get("on") or "").endswith("_supply") or item.get("over") != "each":
            continue
        if item.get("when") in (None, "always"):
            converted.append({
                "path": f"requirements.{item.get('name')}.when",
                "from": {"value": item.get("when"), "unit": None},
                "to": {"value": "running", "unit": None},
                "reason": RUNNING_REASON,
            })
            item["when"] = "running"
    return converted


def period_requirements(requirements):
    """Return ``converted`` entries after dropping ``over``/``when`` where gemini takes none.

    A quantity read over the whole period (``unmet_share``, ``count``, an equipment value)
    takes no ``over`` and no ``when``; gemini refuses either (IMP-012: a pure slip of form, so
    the tool drops it and says so). Edits in place.
    """
    try:
        from gemini.plants.roles import TABLE
    except ImportError:
        return []
    converted = []
    for item in requirements if isinstance(requirements, list) else ():
        if not isinstance(item, dict):
            continue
        reads = TABLE.get(item.get("on"), {}).get(item.get("quantity"))
        if reads is None or getattr(reads, "over", True):
            continue
        for key in ("over", "when"):
            if key in item:
                converted.append({
                    "path": f"requirements.{item.get('name')}.{key}",
                    "from": {"value": item.pop(key), "unit": None},
                    "to": {"value": None, "unit": None},
                    "reason": f"{item.get('quantity')} is read over the whole period: no {key}",
                })
    return converted


def moved_reference_depth(base, data):
    """Return the warning of a reference depth changed while its pressure or temperature stay.

    QA-119: "reservoir at 3000 m" moved ``site.reservoir.reference_depth`` and kept 250 bar(g)
    of 2500 m. The reference depth is where the given values hold, so moving it alone moves them;
    a well depth is the plant's ``params.depth``, where gemini derives both.
    """
    before = ((base or {}).get("site") or {}).get("reservoir") or {}
    after = ((data or {}).get("site") or {}).get("reservoir") or {}
    if before.get("reference_depth") == after.get("reference_depth") or not before:
        return None
    kept = [key for key in ("pressure", "temperature") if key in after and after[key] == before.get(key)]
    if not kept:
        return None
    return (
        f"site.reservoir.reference_depth changed while {' and '.join(kept)} stayed: they are the "
        "values AT the reference depth, so the case now states them at the new depth. A depth "
        "the user or the design chooses for the wells is the plant's params.depth (gemini derives "
        "the pressure and the temperature there from the reference values, the gradient and "
        "the brine); ask the user which is meant before going on"
    )


RANGE_KEYS = ("on", "quantity", "over", "when", "unit")
"""The fields two one-sided requirements share when they are the two ends of one range."""


def joined_ranges(requirements):
    """Return ``(requirements, converted)`` with a lone ``min`` and a lone ``max`` joined (QA-160).

    The brief's 50 to 300 m3/h became ``min_stable_flow`` (min 50) and ``max_production_flow``
    (max 300) in one run of two: the same check, two rows of the verdict for one rule. Two
    requirements on the same ``on``, ``quantity``, ``over``, ``when`` and ``unit``, one with only
    ``min`` and one with only ``max``, are one requirement ``<quantity>_range`` with both.
    """
    if not isinstance(requirements, list):
        return requirements, []
    items, converted = list(requirements), []
    names = {item.get("name") for item in requirements if isinstance(item, dict)}

    def side(item, key):
        other = "max" if key == "min" else "min"
        return isinstance(item, dict) and item.get(key) is not None and item.get(other) is None

    for low in [item for item in items if side(item, "min")]:
        shape = tuple(low.get(key) for key in RANGE_KEYS)
        highs = [item for item in items if side(item, "max")]
        high = next((item for item in highs if tuple(map(item.get, RANGE_KEYS)) == shape), None)
        if high is None or low not in items:
            continue
        name = f"{low.get('quantity')}_range"
        name = name if name not in names - {low.get("name"), high.get("name")} else low["name"]
        joined = {**low, **high, "min": low["min"], "max": high["max"], "name": name}
        items[items.index(low)] = joined
        items.remove(high)
        names = (names - {low.get("name"), high.get("name")}) | {name}
        converted.append({
            "path": f"requirements.{name}",
            "from": {"value": [low.get("name"), high.get("name")], "unit": None},
            "to": {"value": {"min": low["min"], "max": high["max"]}, "unit": low.get("unit")},
            "reason": "a range with both ends is ONE requirement with min and max",
        })
    return items, converted


def exact_ratios(requirements):
    """Return the warning of a per-step requirement with ``min`` equal to ``max`` (QA-203).

    ``reinjection_ratio`` min 1, max 1 fails on round-off of a check, so gemini's example and the
    assumptions document give it a tolerance; geomind invents none, so the user is asked.
    """
    exact = [
        str(item.get("name"))
        for item in (requirements if isinstance(requirements, list) else ())
        if isinstance(item, dict)
        and item.get("over") == "each"
        and item.get("min") is not None
        and item.get("min") == item.get("max")
    ]
    if not exact:
        return None
    return (
        f"requirements {join_names(exact)} have min = max on each step: a computed value equal "
        "to it fails on round-off. Take the tolerance the brief or the Knowledge base gives "
        "(search_rag), or ask the user for it in the confirmation question"
    )


def judged_requirements(data):
    """Return ``converted`` of the case's requirements written as gemini judges them (copied)."""
    if not data.get("requirements"):
        return []
    data["requirements"], joined = joined_ranges(copy.deepcopy(data["requirements"]))
    return joined + running_supply_temperatures(data["requirements"]) + period_requirements(
        data["requirements"]
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


def economics_header(data):
    """Return the header of a new economics file of the case ``data``: format, kind and name.

    The run: ``ask_economics`` on a case without economics wrote the values alone, gemini refused
    the file as an older shape, and the user's approve all was lost (#139).
    """
    name = data.get("name")
    return {"format": 1, "kind": "economics", "name": f"{name} economics" if name else "economics"}


def economics_leaves(node, prefix=""):
    """Return the dotted keys a merge patch of economics sets or removes, ``about`` left out."""
    if not isinstance(node, dict) or "value" in node:
        return [prefix] if prefix else []
    found = []
    for key, child in node.items():
        if not prefix and key == "about":
            continue
        found += economics_leaves(child, f"{prefix}.{key}" if prefix else str(key))
    return found


def sourced_patch(patch):
    """Return ``patch`` with the source of each key it sets or removes without one dropped.

    ``about.sources`` names the row or answer of each value; a value the user changed in chat, or
    a key set to ``null``, kept the Knowledge source of the value it replaced (QA-186). A key the
    patch gives its own source keeps that one.
    """
    about = patch.get("about") if isinstance(patch.get("about"), dict) else {}
    given = about.get("sources") if isinstance(about.get("sources"), dict) else {}
    stale = {key: None for key in economics_leaves(patch) if key not in given}
    if not stale:
        return patch
    return {**patch, "about": {**about, "sources": {**given, **stale}}}


def without_empty_sources(content):
    """Return economics ``content`` without an ``about.sources`` (or ``about``) left empty."""
    about = content.get("about")
    if not isinstance(about, dict) or about.get("sources") != {}:
        return content
    rest = {key: value for key, value in about.items() if key != "sources"}
    kept = {key: value for key, value in content.items() if key != "about"}
    return {**kept, "about": rest} if rest else kept


def edited_economics(context, data, supplied, patch):
    """Set the economics of ``data`` by a merge ``patch``; return the files with the new content.

    The economics file is stored whole as a new content, under the name the case gives it (or
    ``economics.json`` for a case that has none); an economics written inline is patched in place.
    A new file starts from its header (``economics_header``), so a patch of values alone, such as
    ``ask_economics`` sets on approve all, is never refused as an older shape.
    """
    patch = sourced_patch(patch)
    named = data.get("economics")
    if isinstance(named, dict):
        patch = replaced_uncertainties(named, patch)
        data["economics"] = without_empty_sources(merge_patch(named, patch))
        return supplied
    name = checked_name(named or ECONOMICS_FILE)
    data["economics"] = name
    current = file_contents(context, data, supplied).get(name)
    content = json.loads(current) if current is not None else economics_header(data)
    content = without_empty_sources(merge_patch(content, replaced_uncertainties(content, patch)))
    text = json.dumps(content, indent=2, ensure_ascii=False)
    return {**supplied, name: text.encode()}


def changes_files(context, changes, files, supplied):
    """Return ``files`` with each project file a series of ``changes`` names that is not given.

    The case lead named the files in ``changes`` and sent ``files`` alone in another call, again
    and again (#65); a file the changes name is loaded from the project as if it were passed.
    """
    workspace = context.session.workspace
    listed = workspace.files(context.project) if hasattr(workspace, "files") else []
    project = {entry["name"] for entry in listed} if context.project is not None else set()
    needed = unpassed_files(changes or {}, files)
    return [
        name
        for name in needed
        if name in (files or []) or (name in project and name not in supplied)
    ]


def project_files_of(context, names, columns=None):
    """Return ``{name: bytes}`` of the project files ``set_case`` gives to the case.

    ``columns`` renames header names of a file first, so a time column gemini reads as ``time``.
    """
    found = {checked_name(name): project_file(context, "set_case", name) for name in names}
    for name, renames in (columns or {}).items():
        if name in found:
            found[name] = renamed_header(found[name], renames)
    return found


def kept_columns(columns, kept):
    """Return ``columns`` with the renames of an earlier call of the run it does not give.

    QA-222: the case lead sent ``columns`` with files alone, was refused, and left them out of
    the full call; the renames a run gave are kept for each file, a call's own first.
    """
    merged = {name: dict(renames) for name, renames in kept.items()}
    for name, renames in (columns or {}).items():
        merged[name] = {**merged.get(name, {}), **renames}
    return merged or None


def project_or_new(context, source, given):
    """Return ``(source, note)``: ``project`` with no project case and values given is a new case.

    QA-200, QA-222: the first call of every run was ``source='project'`` on a project with only a
    brief and data files, refused with "has no case". With changes, requirements or economics the
    call is set as a new case from them, and the answer says so.
    """
    if source != "project" or not given or context.problem.case is not None:
        return source, None
    try:
        project_case(context)
    except ToolError as error:
        if error.code != "unknown_name" or "has no case" not in str(error):
            raise
        return None, (
            "the project has no case.json, so source='project' loaded nothing: the case is set "
            "from this call's values as a new case; leave source out from now on"
        )
    return source, None


def file_facts(context, names, columns):
    """Return one line per project CSV ``names``: its columns and whether its times have offsets."""
    lines = []
    for name in names:
        try:
            content = project_files_of(context, [name], columns)[name]
        except (ToolError, OSError, ValueError):
            continue
        text = content.decode("utf-8-sig")
        header, _, rest = text.partition("\n")
        header_names = [item.strip() for item in header.rstrip("\r").split(",")]
        read = "" if header_names[0] == TIME_COLUMN else (
            " (read as `time`)" if TIME_NAMES.fullmatch(header_names[0]) else
            f" (rename it: columns={{{name!r}: {{{header_names[0]!r}: 'time'}}}})"
        )
        first = rest.partition("\n")[0].split(",")[0].strip()
        zone = "" if re.search(r"(Z|[+-]\d\d:?\d\d)$", first) else (
            f"; its times ({first!r}) have no offset, so its series needs `time_zone` (an IANA "
            "zone, recorded as an assumption)"
        )
        data = header_names[1:]
        lines.append(
            f"{name}: time column {header_names[0]!r}{read}, data columns {join_names(data)}: each "
            f"series needs `file`, `column`, `unit`{zone}"
        )
    return lines


def files_alone_error(context, files, kept, calls):
    """Return the refusal of ``files`` alone on no case, naming every fix of the next call at once.

    QA-200, QA-222: a files-only call came first in every run. The refusal keeps its ``columns``
    for the next call and says what that call needs: the header, the time, and per file its
    columns and time zone, so the full call is right the first time.
    """
    earlier = (
        f" Your set_case of step {calls[-1]} held the whole case: send that call again, "
        "whole (every section in changes), with only the fix the user's answer or the last error "
        "asks for, such as each series' time_zone."
        if calls
        else ""
    )
    shown = f" The columns {kept!r} are kept for that call." if kept else ""
    facts = file_facts(context, files, kept or None)
    return ToolError(
        f"set_case: files = {files!r} and nothing else; nothing is stored. Send ONE call with "
        "changes that hold the whole case (header, time, site, demand, utilities) and name each "
        "file as the `file` of its series, with requirements and economics in the same call: "
        f"set_case loads the project files the changes name, and files alone set no case.{shown}"
        f"{earlier}",
        code="case_incomplete",
        path="format",
        suggestions=[*facts, *([] if calls else [json.dumps(case_skeleton())])],
    )


def first_case_error(error, data):
    """Return the refusal of a first case without its header, said as what it is (QA-200).

    gemini calls a case without ``format``, ``kind`` and ``name`` "an older shape"; with no case
    stored yet it is a partial patch sent after a refused call, which stored nothing.
    """
    lacking = [key for key in ("format", "kind", "name", "time") if key not in data]
    return ToolError(
        "set_case: no case is stored yet (a refused call stores nothing), so this call is the "
        f"first case and lacks {join_names(lacking)}: send the whole case in one call, every "
        "section of your earlier call with only the fixes its error named",
        code="case_incomplete",
        path=lacking[0] if lacking else error.path,
        suggestions=list(error.suggestions or ()),
    )


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

    Skill `setting-the-case`.
    """
    import gemini as gm

    session_state = getattr(context.session, "__dict__", {})
    calls = session_state.setdefault("case_calls", [])
    kept = session_state.setdefault("case_columns", {})
    if columns:
        kept.update(copy.deepcopy(columns))
    alone = files and source is None and not (changes or requirements or economics)
    if alone and context.problem.case is None:
        raise files_alone_error(context, files, kept, calls)
    step = getattr(getattr(context.session, "state", None), "step", None)
    if changes and step is not None and not DRY_RUN.get():
        calls.append(step)
    previous = context.problem.case
    source, fallback = project_or_new(context, source, changes or requirements or economics)
    base, supplied = base_case(context, source)
    own = {"requirements": requirements, "economics": economics, "files": files, "columns": columns}
    changes, (requirements, economics, files, columns) = moved_arguments(changes, base, own)
    if columns:
        kept.update(copy.deepcopy(columns))
    columns = kept_columns(columns, kept)
    changes, converted = without_empty_units(changes or {})
    files = changes_files(context, changes, files, supplied)
    if files:
        given = await runtime.in_gemini_thread(project_files_of, context, files, columns)
        given, renamed = time_renames(given, columns)
        converted += renamed
        supplied = {**supplied, **given}
    changes, bridged = bridged_units(changes)
    converted += bridged
    changes, derived = pressure_from_elevation(changes)
    converted += derived
    data = merge_patch(base, checked_changes(changes, files))
    if requirements:
        requirements, emptied = without_empty_units(requirements)
        requirements, renamed = bridged_requirements(requirements)
        converted += emptied + renamed
        data["requirements"] = edited_requirements(data.get("requirements"), requirements)
    converted += judged_requirements(data)
    moved = moved_reference_depth(base, data)
    exact = exact_ratios(data.get("requirements"))
    contents = edited_economics(context, data, supplied, economics) if economics else supplied
    origin = given_case(context, source, (base, supplied), (data, contents))
    try:
        version = await store_case(context, data, contents, origin)
    except ToolError as error:
        if base or error.code != "case_incomplete" or not HEADER & set(error.suggestions or ()):
            raise
        raise first_case_error(error, data) from error
    except gm.errors.ValidationError as error:
        retries = case_retries(error, data, supplied, files, columns, changes)
        paths = problem_paths(error)
        if not retries and len(paths) < 2:
            raise
        raise ToolError(
            every_problem(error, paths), code=error.code, path=error.path, suggestions=retries
        ) from error
    needs = await runtime.in_gemini_thread(plants_need, context)
    return {
        **({"note_on_source": fallback} if fallback else {}),
        **loaded_changes(source, previous, data),
        "case": data,
        "version": version,
        "version_is": VERSION_MEANING,
        **({"check": moved} if moved else {}),
        **({"check_requirements": exact} if exact else {}),
        **({"converted": converted} if converted else {}),
        **({"plants_need": needs, "note": PLANTS_NEED_NOTE} if needs else {}),
    }


def case_leaves(node, prefix=""):
    """Return ``{dotted path: value}`` of a case dict, a ``{value, unit}`` one leaf."""
    if not isinstance(node, dict) or not node or "value" in node:
        return {prefix: node} if prefix else {}
    found = {}
    for key, child in node.items():
        found.update(case_leaves(child, f"{prefix}.{key}" if prefix else str(key)))
    return found


STALE_NOTE = "every read_case result from before this call is stale: use this case"


def loaded_changes(source, previous, data):
    """Return ``{changed, note}`` of a case loaded from the project, ``{}`` for any other call.

    QA-227: the project lead briefed with a permeability from before the user's saved case; the
    answer lists each value that differs from the chat's case before, ``[{path, before, after}]``.
    """
    if source != "project":
        return {}
    before, after = case_leaves(previous or {}), case_leaves(data)
    changed = [
        {"path": path, "before": before.get(path), "after": after.get(path)}
        for path in sorted(set(before) | set(after))
        if before.get(path) != after.get(path)
    ]
    return {"changed": changed[:40], "note_on_reads": STALE_NOTE}


VERSION_MEANING = (
    "the problem state's count of changes, not the case version the app shows: never name it to "
    "the user as the case version"
)
"""What ``version`` of a ``set_case`` answer is (QA-114: an agent said version 16, the app 6)."""


PLANTS_NEED_NOTE = (
    "The case reads, but the project's plants need these case values before any design can run: "
    "the case is not complete until each is set or asked for in the one confirmation question."
)


def plants_need(context):
    """Return ``[{path, message, plants}]``: the case values project plants still lack (QA-069).

    ``gm.case.missing`` lists only what the case file needs by itself; what a plant needs (the
    outside air's pressure for an air-cooled unit) only ``gm.check(plant, case)`` names. A plant
    that cannot be checked is left out: the design stage reports it.
    """
    import gemini as gm

    from geomind.tools.gemini.plants import (
        CASE_SECTIONS,
        issue_dict,
        project_plant_names,
        workspace_plant,
    )

    names = project_plant_names(context)
    if not names or context.problem.case is None:
        return []
    try:
        case = case_of(context)
    except (ToolError, gm.errors.ValidationError):
        return []
    found = {}
    for name in names:
        try:
            checked = gm.check(workspace_plant(context, "set_case", name), case)
        except (ToolError, gm.errors.GeminiError, ValueError):
            continue
        for item in map(issue_dict, (issue for issue in checked if not issue.is_warning)):
            path = item.get("path") or ""
            if path.startswith(CASE_SECTIONS):
                entry = found.setdefault(path, {"path": path, "message": item["message"], "plants": []})
                entry["plants"].append(name)
    return list(found.values())


async def set_case_precheck(context, **arguments):
    """Run ``set_case`` without storing anything; raise what gemini refuses (QA-037).

    The engine calls it before it asks the user to approve a ``set_case``, so the user approves
    only a case gemini accepts.
    """
    token = DRY_RUN.set(True)
    try:
        await set_case.function(context, **arguments)
    finally:
        DRY_RUN.reset(token)


set_case.precheck = set_case_precheck


def problem_paths(error):
    """Return the paths of every problem of a rejected case, in gemini's order, each once.

    gemini 0.6.2 judges a whole case at once (request 13): one error holds every issue.
    """
    problems = getattr(error, "problems", None) or ()
    return list(dict.fromkeys(item.get("path") for item in problems if isinstance(item, dict)))


def every_problem(error, paths):
    """Return gemini's message of a rejected case, led by how many paths it names."""
    if len(paths) < 2:
        return shown_message(error)
    return (
        f"set_case: the case has problems at {len(paths)} paths, all listed here; fix every one "
        f"in the next call: {shown_message(error)}"
    )


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

    Skill `setting-the-case`.
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


def unset_section(section, data):
    """Return what ``read_case`` gives for a section the case does not set yet (QA-014).

    An unset section is an answer, not an error: the model reads which sections the case has,
    and the chat shows no failed call.
    """
    return {
        "section": section,
        "unset": True,
        "note": f"the case does not set {section!r} yet; it has {join_names(sorted(data))}",
    }


@tool(effect="read", keeps_result=True)
def read_case(context, section: str | None = None):
    """Return the case of the problem state, one of its sections, its economics or the schema.

    Skill `setting-the-case`.
    """
    import gemini as gm

    if section == "schema":
        return {**gm.Case.schema(), "economics_schema": gm.case.Economics.schema()}
    data = state_case(context)
    found = case_section(context, data, section)
    notice = project_case_notice(context, data)
    if notice is None:
        return found
    return {"project_case": notice, "chat_case": found}


def case_section(context, data, section):
    """Return the state's case ``data``, one of its sections or its economics, for ``read_case``."""
    import gemini as gm

    if section is None:
        return data
    if section == "economics" and not data.get("economics"):
        return unset_section(section, data)
    if section == "economics":
        return economics_of(context, data)
    if section not in data and section in gm.Case.schema()["properties"]:
        return unset_section(section, data)
    if section not in data:
        names = sorted(gm.Case.schema()["properties"])
        raise ToolError(
            f"read_case: section = {section!r}; expected one of {join_names(names)} or 'schema'"
            f"{did_you_mean(section, names)}, and one the case has: {join_names(sorted(data))}",
            path="section",
        )
    return data[section]


def economics_content(data, files):
    """Return the economics of a case dict with its files: inline, its file's JSON, or ``None``."""
    named = data.get("economics")
    if isinstance(named, dict) or named is None:
        return named
    content = files.get(named)
    try:
        return json.loads(content) if content is not None else None
    except ValueError:
        return None


def project_case_notice(context, data):
    """Return what ``read_case`` says when the project's saved case differs from the chat's.

    QA-284: the user saved the discount rate 0.07 on the Case page (case version 5); the chat's
    state kept its own case of version 4, and read_case gave 0.06. The project's latest case is
    compared, economics included; a difference is said with its paths and the call that loads it,
    and nothing is loaded without the user's approval, since the chat's case may hold changes.
    """
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        return None
    try:
        found = workspace.case(context.project)
        mine = file_contents(context, data, {})
    except (OSError, ValueError, ToolError):
        return None
    if found is None:
        return None
    saved, files = found
    before = case_leaves({**data, "economics": economics_content(data, mine)})
    after = case_leaves({**saved, "economics": economics_content(saved, files)})
    paths = [path for path in sorted(set(before) | set(after)) if before.get(path) != after.get(path)]
    if not paths:
        return None
    version = current_case_version(context)
    shown = f"version {version}" if version is not None else "the latest version"
    changed = [{"path": path, "chat": before.get(path), "saved": after.get(path)} for path in paths]
    return {
        "differs": changed[:20],
        "note": (
            f"the project's saved case ({shown}) differs from this chat's case at {len(paths)} "
            "paths, listed here: the user or another chat saved it, or this chat holds changes "
            "not saved. Say so in the answer, and call set_case(source='project') to load the "
            "saved case (the user approves it on a card) before you answer from either"
        ),
    }


def current_case_version(context):
    """Return the version of the project's saved case from its state, or ``None`` when unknown."""
    read = getattr(context.session.workspace, "project_state", None)
    try:
        state = read(context.project) if read is not None else None
    except (OSError, ValueError):
        return None
    return state.get("case_version") if isinstance(state, dict) else None


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

    Skill `setting-the-case`.
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
