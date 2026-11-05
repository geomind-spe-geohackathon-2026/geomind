"""The tools that read and store plants."""

import copy
import json
import re
from typing import Any

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.case import case_of
from geomind.tools.gemini.explain import shown_message
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.skeleton import plant_skeleton
from geomind.tools.gemini.stored import dry_precheck, load_design, save_design
from geomind.utils.strings import did_you_mean, join_names


def plant_schema():
    """Return the schema ``build_plant`` offers as the input ``plant``: gemini's top-level keys.

    Each key of ``gm.plants.schema()`` is named with its type (the classes are in the
    design_lead's plant tree) and the header is required, so a model writes the file's keys
    instead of an empty object; the nested parts are gemini's to validate, when the plant is
    built. ``read_plant`` gives a class's file.
    """
    import gemini as gm

    schema = gm.plants.schema()
    properties = {
        key: {key_name: value for key_name, value in sub.items() if key_name in ("type", "const")}
        or {"type": "object"}
        for key, sub in schema["properties"].items()
    }
    return {
        "type": "object",
        "description": (
            "The plant file: the header format, kind and name, then either type (a class, with "
            "size and params) or modules and connections. Read one with read_plant."
        ),
        "properties": properties,
        "required": list(schema["required"]),
        "minProperties": len(schema["required"]),
        "anyOf": schema["anyOf"],
    }


@tool(effect="read")
def list_plants(context, plant_class: str | None = None, with_schema: bool = False):
    """List the plant classes and the project's plant files; one class in full on request.

    Skill `designing-a-plant`.
    """
    import gemini as gm

    shown = {
        "project_plants": project_plant_names(context),
        "project_versions": [
            {**item, "design": f"design/v{item['version']}"}
            for item in project_designs(context)["plants"]
        ],
        "plants": [
            {"name": name, "summary": gm.plants.get(name).describe()["summary"]}
            for name in gm.plants.names()
        ],
    }
    if plant_class is not None:
        shown.update(class_capabilities(gm, plant_class))
    if with_schema:
        shown["schema"] = gm.plants.schema()
    return shown


def class_capabilities(gm, plant_class):
    """Return the capabilities of one class and the roles it uses; an unknown name is an error."""
    capabilities = gm.plants.capabilities()
    if plant_class not in capabilities:
        raise ToolError(
            f"list_plants: plant_class = {plant_class!r}; expected a name from "
            f"{join_names(capabilities)}{did_you_mean(plant_class, capabilities)}",
            code="unknown_name",
            path="plant_class",
        )
    roles = gm.plants.roles()
    used = capabilities[plant_class]["roles"]
    return {
        "plant_class": plant_class,
        "capabilities": capabilities[plant_class],
        "roles": {role: roles[role] for role in used if role in roles},
    }


def project_plant_names(context):
    """Return the names of the plant files of the run's project, or ``[]`` without one."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        return []
    return sorted(workspace.plants(context.project))


def project_designs(context):
    """Return the project's plant versions and studies, or empty lists (QA-122).

    The backend serves them with ``Workspace.project_designs``; a workspace without it, or a run
    without a project, gives ``{"plants": [], "studies": []}``.
    """
    workspace = context.session.workspace
    read = getattr(workspace, "project_designs", None)
    if read is None or context.project is None:
        return {"plants": [], "studies": []}
    found = read(context.project) or {}
    return {"plants": found.get("plants") or [], "studies": found.get("studies") or []}


def version_plant(context, where, version):
    """Return a saved plant version of the run's project as a gemini plant (QA-122)."""
    import gemini as gm

    workspace = context.session.workspace
    read = getattr(workspace, "plant_version", None)
    if read is None or context.project is None:
        raise ToolError(
            f"{where}: plant_version = {version}; this run's workspace keeps no plant versions; "
            "expected a design, a project_plant or a plant_class",
            code="not_allowed",
            path="plant_version",
        )
    plant = read(context.project, version)
    if plant is None:
        known = [item["version"] for item in project_designs(context)["plants"]]
        raise ToolError(
            f"{where}: plant_version = {version}; expected one of {known} (list_plants "
            "project_versions)",
            code="unknown_name",
            path="plant_version",
        )
    return gm.Plant.from_dict(plant)


def workspace_plant(context, where, name=None):
    """Return the plant file ``name`` of the run's project, or its one file when ``name`` is None.

    A run without a project, a project without plants, an unknown name or several files with no
    name raise a result the model can act on.
    """
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError(
            f"{where}: this run has no project; expected a workspace and one, or a design",
            code="not_allowed",
        )
    plants = workspace.plants(context.project)
    if not plants:
        raise ToolError(
            f"{where}: project {context.project!r} has no plant; expected a design reference",
            code="unknown_name",
            path="design",
        )
    names = ", ".join(sorted(plants))
    if name is None and len(plants) > 1:
        raise ToolError(
            f"{where}: project {context.project!r} has several plants ({names}); name one "
            "(project_plant), a plant class (plant_class) or a stored design (design)",
            code="unknown_name",
            path="project_plant",
        )
    if name is not None and name not in plants:
        raise ToolError(
            f"{where}: project {context.project!r} has no plant {name!r}; expected one of {names}",
            code="unknown_name",
            path="project_plant",
        )
    import gemini as gm

    return gm.Plant.from_dict(plants[name or next(iter(plants))])


def load_plant(context, design, where, project_plant=None):
    """Return a new gemini plant: a stored ``design/<name>`` or a plant file of the project.

    With neither ``design`` nor ``project_plant``, the project's one plant file. A plant is built
    from the file's dict each time, so a run never changes the workspace's plants.
    """
    if design is None:
        return workspace_plant(context, where, project_plant)
    return load_design(context, design, where)


def as_quantity(value):
    """Return a value of ``{"value", "unit"}`` as a gemini ``Quantity``, any other as it is."""
    import gemini as gm

    if isinstance(value, dict) and {"value", "unit"} <= value.keys():
        return gm.units.Quantity(value["value"], value["unit"])
    return value


CASE_SECTIONS = ("site.", "demand.", "utilities.", "time.", "economics.", "requirements")
"""The paths of a case: a value there belongs to the case, never to the plant file."""


def routed_issue(issue):
    """Return an issue at a case path with the suggestion to ask for a case change.

    A design lead never sets the case: a value the case lacks is named in its answer as
    ``case change needed: <path>: <why>``, which the design loop routes to the case lead.
    """
    path = issue.get("path") or ""
    if not path.startswith(CASE_SECTIONS):
        return issue
    hint = (
        f"a value of the case, not of the plant file: hand over with 'case change needed: "
        f"{path}: <why>' in your answer"
    )
    return {**issue, "suggestions": [hint, *(issue.get("suggestions") or [])]}


def issue_dict(issue):
    """Return an ``Issue`` of gemini as compact data: path, code, kind, message, units.

    The message drops the path it starts with, and the accepted units are one ``a|b`` text, so a
    plant's many issues stay small enough for the model to keep.
    """
    problem = issue.problem()
    path, message = problem["path"] or "", problem["message"]
    short = path.removeprefix("params.")
    for prefix in (f"{path}: ", f"{short}: "):
        message = message.removeprefix(prefix)
    item = {"path": path, "code": problem["code"], "kind": issue.kind, "message": message}
    if problem.get("suggestions"):
        item["suggestions"] = list(problem["suggestions"])
    if issue.accepted:
        item["units"] = "|".join(issue.accepted)
    return routed_issue(item)


SCHEDULE_RULES = ("dispatch", "outages")
"""The rules of ``params.control`` gemini's schedule needs: ``simulate`` always runs on its plan.

gemini 0.6.4 refuses a plant without one only when it schedules (``_stated_rules`` in
``gemini/engine/schedule/schedule.py``); ``gm.check`` passes it, so geomind names them.
"""
MODULE_VALUE = re.compile(r"(?P<module>[\w.]+): (?P<name>\w+) = ")
"""A run-time message of gemini about one value: ``d0.riser: esp_depth = None is not ...``."""
MISSING_CODES = ("missing_value", "missing_assumption")


def rule_issues(plant):
    """Return a ``missing`` issue for each rule of ``SCHEDULE_RULES`` the plant does not state.

    ``suggestions`` are the values the parameter accepts, the rules gemini's schedule implements.
    """
    stated = plant.to_dict(structure=True)["params"].get("control") or {}
    parameters = plant.describe()["parameters"]
    issues = []
    for name in SCHEDULE_RULES:
        value = stated.get(name)
        if (value.get("value") if isinstance(value, dict) else value) is not None:
            continue
        parameter = parameters[name]
        issues.append(
            {
                "path": f"params.control.{name}",
                "code": "missing_value",
                "kind": "missing",
                "message": f"no value: {parameter['description']}; simulate's schedule needs it",
                "suggestions": list(parameter["enum"]),
            }
        )
    return issues


def located(plant, message):
    """Return ``params.<module>.<name>`` of a message on one value of a module, else ``None``.

    gemini 0.6.4 gives some run-time refusals without a path (``d0.riser: esp_depth = None ...``);
    the path is taken only when the plant has that module with that parameter.
    """
    found = MODULE_VALUE.match(message)
    if found is None:
        return None
    module = dict(plant.named_modules()).get(found["module"])
    if module is None or found["name"] not in module.describe()["parameters"]:
        return None
    return f"params.{found['module']}.{found['name']}"


def run_issues(plant, case):
    """Return what gemini refuses only when it runs the plant: a one-step run on its schedule.

    gemini 0.6.4 finds some values only in a run, such as the ``esp_depth`` of a well split at its
    pump (``invalid_design``). The run is the first step of ``gm.schedule``'s plan, as
    ``simulate`` runs it; a step that fails is a failed row there, not an issue.
    """
    import gemini as gm

    try:
        gm.simulate(plant, case, plan=gm.schedule(plant, case).iloc[:1])
    except gm.errors.ValidationError as error:
        problems = error.problems
    else:
        return []
    issues = []
    for problem in problems:
        item = {
            "path": problem["path"] or located(plant, problem["message"]) or "",
            "code": problem["code"],
            "kind": "missing" if problem["code"] in MISSING_CODES else "incompatible",
            "message": problem["message"],
        }
        if problem.get("suggestions"):
            item["suggestions"] = list(problem["suggestions"])
        issues.append(routed_issue(item))
    return issues


def plant_issues(context, plant):
    """Return ``{checked_against, issues}`` of a plant: against the state's case when it has one.

    ``gm.check(plant, case)`` is the check that knows what the case fills (``d0.gradient`` empty
    takes it from the case); ``plant.check()`` alone lists such a value as missing. Every value
    ``simulate`` needs is named: the schedule rules gemini's check passes (``rule_issues``), the
    values gemini asks only at a later stage (``stages.later_issues``: a doublet's design values,
    the schedule's supply setpoints), and, once nothing else is missing, what only a run finds
    (``run_issues``, on a probe copy with stand-in setpoints). One patch then fills them all
    (QA-175, QA-171, QA-212). It runs a step of the plant, so the tools call it off the event
    loop.
    """
    import gemini as gm

    from geomind.tools.gemini.stages import later_issues

    rules = rule_issues(plant)
    if context.problem.case is None:
        ruled = {rule["path"] for rule in rules}
        found = [issue_dict(i) for i in plant.check() if i.problem()["path"] not in ruled] + rules
        found += later_issues(plant, found)[0]
        return {"checked_against": "plant", "issues": owned_first(context, found)}
    case = case_of(context)
    checked = gm.check(plant, case)
    ruled = {rule["path"] for rule in rules}
    issues = [issue_dict(i) for i in checked if i.problem()["path"] not in ruled] + rules
    later, probe = later_issues(plant, issues, case)
    if not rules and all(issue.is_warning for issue in checked):
        issues += later + probe_run_issues(plant, probe, case)
    else:
        issues += later
    return {"checked_against": "case", "issues": owned_first(context, issues)}


def probe_run_issues(plant, probe, case):
    """Return what a run finds: on ``plant``, or on ``probe`` when it stands in for setpoints.

    A probe run's issues are kept only when they name a value the plant lacks (QA-175).
    """
    from geomind.tools.gemini.stages import lacking_values

    if probe is None:
        return run_issues(plant, case)
    return lacking_values(run_issues(probe, case))


def owned_first(context, issues):
    """Return ``issues`` for an engineer: its own first, each other one with its ``owner`` (IMP-014).

    170 patch_plant calls were refused as another engineer's part: the engineer saw every
    missing value as its own. Outside an engineer's call the issues are unchanged.
    """
    from geomind.tools.gemini.ownership import discipline_of, owner_of

    discipline = discipline_of(context)
    owners = (getattr(context.problem, "design", None) or {}).get("owners") or {}
    if discipline is None or not owners:
        return issues
    own, others = [], []
    for item in issues:
        path = str(item.get("path") or "").removeprefix("params.")
        owner = owner_of(path, owners) if path else None
        if owner in (None, discipline):
            own.append(item)
        else:
            others.append({**item, "owner": f"{owner} engineer: hand it back, not yours"})
    return own + others


def shown_ranges(plant):
    """Return the search ranges of a plant as ``{path: {min, max}}`` in gemini's display units.

    A bound of a leaf with a unit is ``{value, unit}`` (MW, m3/h, degC); a bound of a count such as
    ``size.doublets`` is a plain number. gemini writes them so (``to_dict(units="display")``).
    """
    data = plant.to_dict(units="display")
    shown = {}
    for path in plant.ranges:
        section, _, leaf = path.partition(".") if path.startswith("size.") else ("params", "", path)
        node = data[section]
        for part in leaf.split("."):
            node = node[part]
        unit = node.get("unit")
        shown[path] = {
            side: bound if unit is None else {"value": bound, "unit": unit}
            for side, bound in node["range"].items()
        }
    return shown


def editable_dict(plant, units=None):
    """Return the plant file to show and patch: a class plant's own file, else the full form.

    A class plant's file is its class, its size and the values given (QA-247, QA-260): it builds
    back as it is, and a patch of ``size`` resizes it. Its full form lists the modules the class
    makes from its size (``d1`` of 2 doublets), which ``build_plant`` refuses beside a ``type``.
    """
    data = plant.to_dict(units=units)
    if "type" in data:
        return data
    return plant.to_dict(structure=True, units=units)


def plant_view(plant):
    """Return the plant file in gemini's display units, with its search ranges and options.

    gemini 0.6.3 writes a plant file in display units (MW, degC, bar, m3/h; request 30), so the
    model quotes each value as given and converts none. A class plant is shown as its own file,
    with the names of the modules its class makes under ``modules``.
    """
    view = {"plant": editable_dict(plant, units="display")}
    if "type" in view["plant"]:
        view["modules"] = sorted(plant.to_dict(structure=True).get("modules") or {})
    return {
        **view,
        "ranges": shown_ranges(plant),
        "options": {path: list(options) for path, options in plant.options.items()},
    }


@tool(
    effect="read",
    late_schemas={"design": reference_schema("design", optional=True)},
    keeps_result=True,
)
async def read_plant(
    context,
    design: str | None = None,
    plant_class: str | None = None,
    project_plant: str | None = None,
    plant_version: int | None = None,
):
    """Read a project plant file or version, a stored design or a plant class: file, ranges, issues.

    Skill `designing-a-plant`.
    """
    import gemini as gm

    chosen = (design, plant_class, project_plant, plant_version)
    if sum(argument is not None for argument in chosen) > 1:
        raise ToolError(
            "read_plant: design, plant_class, project_plant and plant_version are mutually "
            "exclusive; expected one of them",
            path="design",
        )
    if plant_class is not None:
        plant = gm.plants.get(plant_class)
    elif plant_version is not None:
        plant = version_plant(context, "read_plant", plant_version)
    else:
        plant = load_plant(context, design, "read_plant", project_plant)
    issues = await runtime.in_gemini_thread(plant_issues, context, plant)
    stored = stored_reference(context, design, project_plant, plant_version)
    return {**stored, **plant_view(plant), **issues}


def stored_reference(context, design, project_plant, plant_version):
    """Return ``{design, use}``: the reference a read plant is stored under (QA-221, QA-247).

    A project plant or plant version is a stored design already: the design tools take it by its
    reference, so it is never typed again into ``build_plant``.
    """
    if plant_version is not None:
        reference = f"design/v{plant_version}"
    elif design is not None:
        reference = design
    elif project_plant is not None or project_plant_names(context):
        reference = f"design/{project_plant or project_plant_names(context)[0]}"
    else:
        return {}
    return {
        "design": reference,
        "use": (
            f"{reference} is stored: pass it as design to patch_plant, set_ranges, simulate and "
            "the studies; never type it again into build_plant"
        ),
    }


CHOICE_PARAMS = (("backup",), ("control", "outages"), ("control", "dispatch"))
"""Plant options a model often sends as a bare string (QA-052): ``"none"`` for ``{"value": "none"}``."""


def listed_changes(changes):
    """Return a change list ``[{path, value, ...}]`` as the merge patch ``{path: value}``.

    The design engineers hand back their changes so (``agents/design/proposal.py``); the lead
    passes all of them in one call. ``source`` and ``reason`` are the engineers' record, not plant
    values. A dict passes unchanged.
    """
    if not isinstance(changes, list):
        return changes
    patch = {}
    for index, item in enumerate(changes):
        if not isinstance(item, dict) or not isinstance(item.get("path"), str) or "value" not in item:
            raise ToolError(
                f"patch_plant: changes[{index}] = {json.dumps(item)[:120]}; expected "
                "{path, value} with path a dotted plant path such as 'params.d0.depth'",
                path=f"changes.{index}",
            )
        path = item["path"].removeprefix("plant.")
        patch[path] = item["value"]
    return patch


def wrapped_choices(plant):
    """Return ``plant`` with each plant option given as a bare string written ``{"value": ...}``."""
    params = plant.get("params") if isinstance(plant, dict) else None
    if not isinstance(params, dict):
        return plant
    params = copy.deepcopy(params)
    for path in CHOICE_PARAMS:
        node = params
        for part in path[:-1]:
            node = node.get(part) if isinstance(node, dict) else None
        if isinstance(node, dict) and isinstance(node.get(path[-1]), str):
            node[path[-1]] = {"value": node[path[-1]]}
    return {**plant, "params": params}


VERSION_NAME = re.compile(r"v\d+")
"""A design name that is the alias of a project plant version: ``design/v3`` is version 3."""


def free_name(name, where):
    """Raise unless ``name`` is free to store a new design under: ``v<N>`` is a version's alias."""
    if VERSION_NAME.fullmatch(str(name)):
        raise ToolError(
            f"{where}: name = {name!r}; design/{name} is the project's plant version "
            f"{name[1:]}, stored already: pass design/{name} as the design to work on it, or "
            "give a new design another name",
            code="invalid_input",
            path="name",
        )


@tool(effect="write", late_schemas={"plant": plant_schema})
async def build_plant(context, plant: dict[str, Any], name: str, from_class: str | None = None):
    """Build a plant from a plant file and store it as design/<name>; return its issues.

    Skill `designing-a-plant`.
    """
    import gemini as gm

    free_name(name, "build_plant")
    if not plant:
        example = {**plant_skeleton(), "type": "<plant class>"}
        raise ToolError(
            "build_plant: plant = {}; it is empty: expected the plant file, its header and its "
            "type or its modules and connections",
            path="plant",
            suggestions=[json.dumps(example)],
        )
    if isinstance(plant.get("format"), str) and plant["format"].strip().isdigit():
        plant = {**plant, "format": int(plant["format"])}
    plant = wrapped_choices(plant)
    if from_class is not None:
        plant = await runtime.in_gemini_thread(extended_plant, plant, from_class)
    try:
        built = await runtime.in_gemini_thread(gm.Plant.from_dict, plant)
    except gm.errors.ValidationError as error:
        foreign = foreign_modules(gm, plant) if from_class is None else []
        if foreign:
            raise class_refusal(error, plant["type"], foreign) from error
        if error.code != "old_format":
            raise
        raise ToolError(
            shown_message(error),
            code=error.code,
            path=error.path,
            suggestions=[*error.suggestions, json.dumps(plant_skeleton())],
        ) from error
    design = await save_design(context, name, built)
    found = await runtime.in_gemini_thread(plant_issues, context, built)
    twins = await runtime.in_gemini_thread(stored_twins, context, built)
    return {"design": design, **found, **twins}


def stored_plants(context):
    """Yield ``(reference, plant)`` for each project plant file and plant version (QA-278)."""
    import gemini as gm

    workspace = context.session.workspace
    if workspace is None or context.project is None:
        return
    files = getattr(workspace, "plants", None)
    for name, data in sorted(((files(context.project) if files else None) or {}).items()):
        yield f"design/{name}", lambda data=data: gm.Plant.from_dict(data)
    for item in project_designs(context)["plants"]:
        version = item.get("version")
        yield f"design/v{version}", lambda version=version: version_plant(
            context, "build_plant", version
        )


def stored_twins(context, built):
    """Return ``{stored_as, warning}`` when ``built`` is of a project plant's class (QA-278).

    A project plant re-typed by hand is another plant: the run optimised a re-built
    HeatingFullCoolingPlant to 52.5 EUR/MWh, the stored one to 32.4. The warning names the stored
    plant to work on and whether the built one differs from it.
    """
    kind = built.to_dict().get("type")
    if not kind:
        return {}
    shown = built.to_dict(structure=True)
    same, other = [], []
    for reference, load in stored_plants(context):
        try:
            plant = load()
        except Exception:  # noqa: BLE001 - a stored plant gemini cannot read is no twin
            continue
        if plant.to_dict().get("type") != kind:
            continue
        (same if plant.to_dict(structure=True) == shown else other).append(reference)
    if not same and not other:
        return {}
    told = "is a stored plant" if same else f"differs from the stored {kind}"
    warning = f"{told} (stored_as): work on that design; never build a stored plant again"
    return {"stored_as": same or other, "warning": warning}


def foreign_modules(gm, plant):
    """Return the modules a class plant names (in ``modules``, ``optional``) its class lacks.

    The run: ``optional: ["thermal_storage"]`` on a ``HeatingHeatPumpCoolingPlant`` was "expected
    a module of the plant", and the process engineer spent its 15 steps on a free plant (#143).
    """
    kind = plant.get("type")
    if not isinstance(kind, str) or kind not in gm.plants.names():
        return []
    own = set(gm.plants.get(kind).to_dict(structure=True).get("modules") or {})
    named = list(plant.get("modules") or {}) + [
        item for item in plant.get("optional") or [] if isinstance(item, str)
    ]
    return sorted({item for item in named if item not in own})


def class_refusal(error, kind, foreign):
    """Return the error of a class plant with modules its class lacks, naming how to add them."""
    return ToolError(
        f"{shown_message(error)}. build_plant: {join_names(foreign)} is no module of the class "
        f"{kind}, and a plant with type takes only its class's modules. To add it: build_plant "
        f"with from_class={kind!r} and a plant without type that holds only the added modules "
        "(with their type), the connections of each of their ports (describe_module lists them; "
        "one at a port that takes one connection replaces the class's), and optional or choices; "
        "the class gives every other module and connection",
        code="unknown_name",
        path="from_class",
        suggestions=[kind],
    )


def extended_plant(plant, from_class):
    """Return the free plant file of a class with the modules and connections of ``plant`` added.

    The class's own file (``structure=True``) gives the modules, connections, size, params and
    fluids; ``plant`` adds or replaces modules, merges params, and adds its connections, each
    replacing the class's at a port that takes one connection. Its other keys win; ``type`` goes.
    """
    import gemini as gm

    from geomind.tools.gemini.case import merge_patch

    names = gm.plants.names()
    if from_class not in names:
        raise ToolError(
            f"build_plant: from_class = {from_class!r}; expected a plant class from list_plants"
            f"{did_you_mean(from_class, names)}",
            code="unknown_name",
            path="from_class",
        )
    base = class_base(gm, from_class, plant.get("size"))
    modules = {**(base.get("modules") or {}), **(plant.get("modules") or {})}
    given = [item for item in plant.get("connections") or [] if isinstance(item, dict)]
    single = single_ports(gm, modules, given)
    kept = [
        item
        for item in base.get("connections") or []
        if item.get("source") not in single and item.get("target") not in single
    ]
    extended = {key: value for key, value in base.items() if key != "type"}
    extended.update({key: value for key, value in plant.items() if key != "type"})
    extended["modules"] = modules
    extended["connections"] = kept + given
    params = merge_patch(base.get("params") or {}, plant.get("params") or {})
    if params:
        extended["params"] = params
    else:
        extended.pop("params", None)
    return extended


def class_base(gm, from_class, size):
    """Return the full form of a class plant at ``size`` (QA-260: 2 doublets stay 2)."""
    if not size:
        return gm.plants.get(from_class).to_dict(structure=True)
    header = {"format": 1, "kind": "plant", "name": from_class, "type": from_class, "size": size}
    return gm.Plant.from_dict(header).to_dict(structure=True)


def single_ports(gm, modules, connections):
    """Return the ports ``connections`` use that take one connection (a port not ``many``).

    A port whose module type is not found counts as one that takes many: the class's connection
    stays, and gemini names a port used twice.
    """
    found = set()
    for item in connections:
        for side in ("source", "target"):
            port = item.get(side)
            if isinstance(port, str) and port_takes_one(gm, modules, port):
                found.add(port)
    return found


def port_takes_one(gm, modules, port):
    """Tell whether a port ``<module path>.<port>`` of the plant's modules takes one connection."""
    *path, name = port.split(".")
    node = {"modules": modules}
    for part in path:
        node = (node.get("modules") or {}).get(part) if isinstance(node, dict) else None
    kind = node.get("type") if isinstance(node, dict) else None
    if not isinstance(kind, str) or not path:
        return False
    try:
        description = gm.modules.get(kind)().describe()
    except gm.errors.GeminiError:
        return False
    ports = {**description.get("inlets", {}), **description.get("outlets", {})}
    item = ports.get(name)
    return isinstance(item, dict) and not item.get("port", {}).get("many", False)


STRUCTURE_KEYS = {"modules", "connections", "fluids", "type"}
"""The keys of a patch that change a plant's structure: it is applied to the full form."""


@tool(effect="write", late_schemas={"design": reference_schema("design")})
async def patch_plant(
    context, design: str, changes: dict[str, Any] | list[dict[str, Any]], name: str
):
    """Change a stored design by a small patch, stored as design/<name>, and list what is missing.

    Skill `designing-a-plant`.
    """
    import gemini as gm

    from geomind.tools.gemini.case import merge_patch
    from geomind.tools.gemini.ownership import check_ownership, placed_parameters

    free_name(name, "patch_plant")
    loaded = load_design(context, design, "patch_plant")
    plant = loaded.to_dict(structure=True)
    changes = wrapped_choices(placed_parameters(listed_changes(changes), plant))
    check_ownership(context, changes, "patch_plant", plant)
    if not STRUCTURE_KEYS & set(changes):
        plant = editable_dict(loaded)
    patched = merge_patch(plant, changes)
    if patched == plant:
        raise ToolError(
            f"patch_plant: changes = {json.dumps(changes)[:200]}; they change nothing in "
            f"{design}, so nothing was stored. Give each value to change at its plant path, "
            "such as {\"params.d0.depth\": {\"value\": 2500, \"unit\": \"m\"}}, or the engineers' "
            "list of {path, value, source}",
            code="no_change",
            path="changes",
        )
    built = await runtime.in_gemini_thread(gm.Plant.from_dict, patched)
    stored = await save_design(context, name, built)
    issues = await runtime.in_gemini_thread(plant_issues, context, built)
    return {"design": stored, **issues, "missing": len(issues["issues"])}


def plant_difference(base, other):
    """Return the JSON merge patch that turns ``base`` into ``other``; a list is one value."""
    if not isinstance(base, dict) or not isinstance(other, dict):
        return other
    patch = {key: None for key in base if key not in other}
    for key, value in other.items():
        if key not in base:
            patch[key] = value
        elif base[key] != value:
            patch[key] = plant_difference(base[key], value)
    return patch


def leaf_changes(patch, prefix=""):
    """Return ``{dotted path: value}`` of every leaf a merge patch sets or removes."""
    if not isinstance(patch, dict) or not patch:
        return {prefix: patch}
    found = {}
    for key, value in patch.items():
        found.update(leaf_changes(value, f"{prefix}.{key}" if prefix else key))
    return found


@tool(effect="write", late_schemas={"base": reference_schema("design")})
async def merge_designs(context, base: str, designs: list[str], name: str):
    """Join the designs the engineers patched side by side from ``base``, stored as design/<name>.

    Skill `designing-a-plant`.
    """
    import gemini as gm

    from geomind.tools.gemini.case import merge_patch

    start = load_design(context, base, "merge_designs").to_dict(structure=True)
    merged, setters = start, {}
    for design in designs:
        patch = plant_difference(
            start, load_design(context, design, "merge_designs").to_dict(structure=True)
        )
        for path, value in leaf_changes(patch).items():
            earlier = setters.get(path)
            if earlier is not None and earlier[1] != value:
                raise ToolError(
                    f"merge_designs: {path} is set by {earlier[0]} and differently by {design}; "
                    "send it back to its owner with both values",
                    code="invalid_input",
                    path="designs",
                )
            setters[path] = (design, value)
        merged = merge_patch(merged, patch)
    built = await runtime.in_gemini_thread(gm.Plant.from_dict, merged)
    stored = await save_design(context, name, built)
    issues = await runtime.in_gemini_thread(plant_issues, context, built)
    return {"design": stored, **issues, "missing": len(issues["issues"])}


def plant_union(plants, name):
    """Return gemini's superstructure of ``plants`` (``gm.plants.union``) and its ``union``."""
    import gemini as gm

    joined = gm.plants.union(plants, name=name)
    return joined, joined.union


@tool(effect="write", late_schemas={"designs": reference_schema("design", many=True)})
async def union_designs(context, designs: list[str], name: str):
    """Join alternative designs into one superstructure by gemini, stored as design/<name>.

    Skill `comparing-designs`.
    """
    from geomind.tools.gemini.study import to_plain

    plants = [load_design(context, design, "union_designs") for design in designs]
    by_plant = {plant.name: design for plant, design in zip(plants, designs)}
    built, union = await runtime.in_gemini_thread(plant_union, plants, name)
    stored = await save_design(context, name, built)
    structures = {by_plant.get(plant, plant): item for plant, item in union["structures"].items()}
    notes = [
        {
            **note,
            "values": {
                by_plant.get(plant, plant): value for plant, value in note["values"].items()
            },
        }
        for note in to_plain(union["notes"])
    ]
    issues = await runtime.in_gemini_thread(plant_issues, context, built)
    return {
        "design": stored,
        "structures": structures,
        "notes": notes,
        **issues,
        "missing": len(issues["issues"]),
    }


@tool(effect="write", sets_input=True, late_schemas={"design": reference_schema("design")})
async def set_ranges(
    context,
    design: str,
    ranges: dict[str, dict[str, Any]],
    name: str,
    options: dict[str, list[Any]] | None = None,
):
    """Set search ranges on a design: they come from the user or the case, so ask_user first.

    Skill `designing-a-plant`.
    """
    import gemini as gm

    plant = load_design(context, design, "set_ranges")
    later = []
    for path, bounds in sorted(ranges.items(), key=lambda item: not item[0].startswith("size.")):
        try:
            plant.set_range(
                path, min=as_quantity(bounds.get("min")), max=as_quantity(bounds.get("max"))
            )
        except gm.errors.ValidationError as error:
            later.append(later_doublet(plant, path, error))
    for path, values in (options or {}).items():
        plant.set_options(path, [as_quantity(value) for value in values])
    stored = {"design": await save_design(context, name, plant), **plant_view(plant)}
    return {**stored, "not_set": later} if later else stored


DOUBLET_PATH = re.compile(r"d(?P<index>\d+)\.")
"""A path on one doublet of a plant: ``d2.nominal_flow`` is on its third doublet."""


def later_doublet(plant, path, error):
    """Return why a range on a doublet the plant does not have yet was not set, or raise.

    QA-253: ``d2.nominal_flow`` on a plant of 2 doublets with ``size.doublets`` 1-3 was refused,
    and the lead narrowed the size range to 2 to get it through. A doublet a search adds takes
    d0's values and range, so the range is named here, never dropped in silence; any other
    refusal is gemini's.
    """
    found = DOUBLET_PATH.match(path)
    doublets = (getattr(plant, "size", None) or {}).get("doublets")
    most = (shown_ranges(plant).get("size.doublets") or {}).get("max")
    if found is None or doublets is None or most is None:
        raise error
    index = int(found["index"])
    if index < doublets or index >= most:
        raise error
    shared = f"d0{path[found.end() - 1:]}"
    return {
        "path": path,
        "reason": (
            f"the plant has {doublets} doublet(s) now; d{index} exists only once the search "
            f"sizes it to {index + 1} or more, and then takes d0's values and the range of "
            f"{shared}: set {shared} to the range every doublet may use. size.doublets keeps "
            f"its range up to {most}; say in your answer what the search covered"
        ),
    }


build_plant.precheck = dry_precheck(build_plant.function)
patch_plant.precheck = dry_precheck(patch_plant.function)
merge_designs.precheck = dry_precheck(merge_designs.function)
