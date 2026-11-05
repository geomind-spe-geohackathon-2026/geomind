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


def judged_requirements(data):
    """Return ``converted`` of the case's requirements written as gemini judges them (copied)."""
    if not data.get("requirements"):
        return []
    data["requirements"] = copy.deepcopy(data["requirements"])
    return running_supply_temperatures(data["requirements"]) + period_requirements(
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


def edited_economics(context, data, supplied, patch):
    """Set the economics of ``data`` by a merge ``patch``; return the files with the new content.

    The economics file is stored whole as a new content, under the name the case gives it (or
    ``economics.json`` for a case that has none); an economics written inline is patched in place.
    A new file starts from its header (``economics_header``), so a patch of values alone, such as
    ``ask_economics`` sets on approve all, is never refused as an older shape.
    """
    named = data.get("economics")
    if isinstance(named, dict):
        data["economics"] = merge_patch(named, patch)
        return supplied
    name = checked_name(named or ECONOMICS_FILE)
    data["economics"] = name
    current = file_contents(context, data, supplied).get(name)
    content = json.loads(current) if current is not None else economics_header(data)
    text = json.dumps(merge_patch(content, patch), indent=2, ensure_ascii=False)
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

    alone = files and source is None and not (changes or requirements or economics)
    calls = getattr(context.session, "__dict__", {}).setdefault("case_calls", [])
    if alone and context.problem.case is None:
        earlier = (
            f" Your set_case of step {calls[-1]} held the whole case: send that call again, "
            "whole (every section in changes, the files and columns), with only the fix the "
            "user's answer or the last error asks for, such as each series' time_zone."
            if calls
            else ""
        )
        raise ToolError(
            f"set_case: files = {files!r} and nothing else; expected changes that name each file "
            "as the `file` of its series: set_case loads the project files the changes name, so "
            f"`files` is not needed, and files alone set no case.{earlier}",
            code="case_incomplete",
            path="format",
            suggestions=[] if calls else [json.dumps(case_skeleton())],
        )
    step = getattr(getattr(context.session, "state", None), "step", None)
    if changes and step is not None and not DRY_RUN.get():
        calls.append(step)
    base, supplied = base_case(context, source)
    own = {"requirements": requirements, "economics": economics, "files": files, "columns": columns}
    changes, (requirements, economics, files, columns) = moved_arguments(changes, base, own)
    files = changes_files(context, changes, files, supplied)
    if files:
        given = await runtime.in_gemini_thread(project_files_of, context, files, columns)
        supplied = {**supplied, **given}
    changes, converted = bridged_units(changes or {})
    changes, derived = pressure_from_elevation(changes)
    converted += derived
    data = merge_patch(base, checked_changes(changes, files))
    if requirements:
        requirements, renamed = bridged_requirements(requirements)
        converted += renamed
        data["requirements"] = edited_requirements(data.get("requirements"), requirements)
    converted += judged_requirements(data)
    contents = edited_economics(context, data, supplied, economics) if economics else supplied
    origin = given_case(context, source, (base, supplied), (data, contents))
    try:
        version = await store_case(context, data, contents, origin)
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
        "case": data,
        "version": version,
        **({"converted": converted} if converted else {}),
        **({"plants_need": needs, "note": PLANTS_NEED_NOTE} if needs else {}),
    }


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


@tool(effect="read")
def read_case(context, section: str | None = None):
    """Return the case of the problem state, one of its sections, its economics or the schema.

    Skill `setting-the-case`.
    """
    import gemini as gm

    if section == "schema":
        return {**gm.Case.schema(), "economics_schema": gm.case.Economics.schema()}
    data = state_case(context)
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
