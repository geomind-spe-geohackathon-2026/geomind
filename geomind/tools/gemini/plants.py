"""The tools that read and store plants."""

from typing import Any

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.case import case_of
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.stored import load_design, save_design
from geomind.utils.strings import did_you_mean, join_names


def plant_schema():
    """Return the short schema ``build_plant`` offers as the input ``plant``.

    The full schema is large and is sent with every call, so the tool offers an object and the
    two ways a plant file is given; ``list_plants`` ``schema`` returns gemini's whole schema and
    ``read_plant`` a class's file. Validation is gemini's, when the plant is built.
    """
    return {
        "type": "object",
        "description": (
            "The plant file: a class file has type, a module file has modules and connections. "
            "Read one with read_plant; list_plants(with_schema=true) gives the full schema."
        ),
        "anyOf": [{"required": ["type"]}, {"required": ["modules", "connections"]}],
    }


@tool(effect="read")
def list_plants(context, plant_class: str | None = None, with_schema: bool = False):
    """List the plant classes and the project's plant files; one class in full on request.

    Without arguments: ``project_plants``, the names of the project's plant files (``read_plant``
    ``project_plant`` reads one; empty without a project or plants), and ``plants``, each class
    with its summary. With ``plant_class``: its ``capabilities`` (``roles``, whether it is
    ``schedulable`` and ``ranges``, the leaves of the plant file that may state a search range,
    which ``set_ranges`` sets) and ``roles``, the quantities a module of each of its roles reports.
    With ``with_schema`` true: ``schema``, gemini's schema of the plant file ``build_plant`` takes.
    """
    import gemini as gm

    shown = {
        "project_plants": project_plant_names(context),
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


def issue_dict(issue):
    """Return an ``Issue`` of gemini as plain data: its problem with its kind and accepted units."""
    return {
        **issue.problem(),
        "kind": issue.kind,
        "quantity": issue.quantity,
        "accepted": list(issue.accepted),
    }


def plant_issues(context, plant):
    """Return ``{checked_against, issues}`` of a plant: against the state's case when it has one.

    ``gm.check(plant, case)`` is the check that knows what the case fills (``d0.gradient`` empty
    takes it from the case); ``plant.check()`` alone lists such a value as missing.
    """
    import gemini as gm

    if context.problem.case is None:
        return {"checked_against": "plant", "issues": [issue_dict(i) for i in plant.check()]}
    issues = gm.check(plant, case_of(context))
    return {"checked_against": "case", "issues": [issue_dict(i) for i in issues]}


def shown_ranges(plant):
    """Return the search ranges of a plant as ``{path: {min, max}}`` in gemini's display units.

    A bound of a leaf with a unit is ``{value, unit}`` (MW, m3/h, degC); a bound of a count such as
    ``size.doublets`` is a plain number.
    """
    import gemini as gm

    table = gm.units.display.by_si_unit()
    data = plant.to_dict()
    shown = {}
    for path in plant.ranges:
        section, _, leaf = path.partition(".") if path.startswith("size.") else ("params", "", path)
        node = data[section]
        for part in leaf.split("."):
            node = node[part]
        unit = node.get("unit")
        shown[path] = {
            side: (
                bound
                if unit is None
                else gm.units.display.shown(gm.units.Quantity(bound, unit), table).to_dict()
            )
            for side, bound in node["range"].items()
        }
    return shown


def plant_view(plant):
    """Return the plant file with its search ranges and options, as the model reads a plant."""
    return {
        "plant": plant.to_dict(structure=True),
        "ranges": shown_ranges(plant),
        "options": {path: list(options) for path, options in plant.options.items()},
    }


@tool(effect="read", late_schemas={"design": reference_schema("design", optional=True)})
def read_plant(
    context,
    design: str | None = None,
    plant_class: str | None = None,
    project_plant: str | None = None,
):
    """Read a project plant file, a stored design or a plant class: file, ranges, issues.

    Give one of ``project_plant`` (a name from ``list_plants`` ``project_plants``),
    ``design`` as ``design/<name>`` or ``plant_class`` (a name from ``list_plants``); with none,
    the project's plant is read when it has exactly one file. Returns ``plant`` (the plant file
    ``build_plant`` takes), ``ranges`` (each searchable leaf as ``{min, max}`` in display units),
    ``options`` and ``issues`` (what is wrong or missing, with path, kind, quantity and accepted
    units). With a case in the state the issues come from ``gm.check(plant, case)`` and
    ``checked_against`` is ``case``; without one they come from the plant alone (``plant``),
    which lists as missing what the case would fill. A class is read without values: every
    parameter it needs is missing until you fill it in a plant file.
    """
    import gemini as gm

    if sum(argument is not None for argument in (design, plant_class, project_plant)) > 1:
        raise ToolError(
            "read_plant: design, plant_class and project_plant are mutually exclusive; "
            "expected one of them",
            path="design",
        )
    if plant_class is not None:
        plant = gm.plants.get(plant_class)
    else:
        plant = load_plant(context, design, "read_plant", project_plant)
    return {**plant_view(plant), **plant_issues(context, plant)}


@tool(effect="write", late_schemas={"plant": plant_schema})
async def build_plant(context, plant: dict[str, Any], name: str):
    """Build a plant from a plant file and store it as design/<name>; return its issues.

    ``plant`` is the plant file (``read_plant`` shows one). Every value with a dimension is
    ``{"value", "unit"}``. A file gemini cannot read is an error with gemini's problems
    (``path``, ``message``, ``suggestions`` such as the name probably meant) and nothing is
    stored. A file that builds is stored even with ``issues`` (the values still missing, checked
    as in ``read_plant``): fill them in a new file or with ``simulate`` ``changes``.
    """
    import gemini as gm

    built = await runtime.in_gemini_thread(gm.Plant.from_dict, plant)
    design = await save_design(context, name, built)
    return {"design": design, **plant_issues(context, built)}


@tool(effect="write", late_schemas={"design": reference_schema("design")})
async def set_ranges(
    context,
    design: str,
    ranges: dict[str, dict[str, Any]],
    name: str,
    options: dict[str, list[Any]] | None = None,
):
    """Set search ranges on a design: they come from the user or the case, so ask_user first.

    Propose values with ask_user and set them only after the user confirms. The result is stored
    as design/<name>.

    ``ranges`` is ``{path: {"min": {"value", "unit"}, "max": {"value", "unit"}}}``; a count such
    as ``size.doublets`` takes plain numbers; a side left out is open and a leaf with neither
    loses its range. ``options`` is ``{path: [value, ...]}`` for a leaf that takes one of a
    list. A path is the leaf of the plant file without ``params.``: ``size.doublets``,
    ``depth``, ``heat_pump.capacity``, ``d0.nominal_flow``; ``list_plants`` ``capabilities`` and
    ``read_plant`` ``ranges`` name them. An unknown path, or a bound gemini refuses, is gemini's
    error with its path (for an unknown path, the valid ones). A study (``optimize``) searches
    the leaves that state a range; the design read is not changed.
    """
    plant = load_design(context, design, "set_ranges")
    for path, bounds in ranges.items():
        plant.set_range(
            path, min=as_quantity(bounds.get("min")), max=as_quantity(bounds.get("max"))
        )
    for path, values in (options or {}).items():
        plant.set_options(path, [as_quantity(value) for value in values])
    return {"design": await save_design(context, name, plant), **plant_view(plant)}
