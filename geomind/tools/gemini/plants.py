"""The tools that read and store plants."""

import asyncio
from typing import Any

from geomind.errors import ToolError, UnknownNameError
from geomind.tools.base import tool
from geomind.tools.gemini.case import case_of
from geomind.tools.gemini.stored import load_design, save_design


def plant_schema():
    """Return gemini's plant schema, which ``build_plant`` offers as the input ``plant``."""
    import gemini as gm

    return gm.plants.schema()


@tool(effect="read")
def list_plants():
    """List the plant classes with their summary, capabilities (with ranges) and roles.

    ``capabilities`` maps a class to its ``roles``, whether it is ``schedulable`` and its
    ``ranges``, the leaves of the plant file that may state a search range (``set_ranges`` sets
    them). ``roles`` maps each role to the quantities a module of that role reports.
    """
    import gemini as gm

    return {
        "plants": [
            {"name": name, "summary": gm.plants.get(name).describe()["summary"]}
            for name in gm.plants.names()
        ],
        "capabilities": gm.plants.capabilities(),
        "roles": gm.plants.roles(),
    }


def project_plant(context, where):
    """Return the plant of the run's project, or raise a result the model can act on."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError(
            f"{where}: this run has no project; expected a workspace and one, or a design",
            code="not_allowed",
        )
    try:
        plant = workspace.plant(context.project)
    except UnknownNameError as error:
        raise ToolError(
            f"{where}: {error}; name a plant class (plant_class) or a stored design (design)",
            code="unknown_name",
            path="design",
        ) from error
    if plant is None:
        raise ToolError(
            f"{where}: project {context.project!r} has no plant; expected a design reference",
            code="unknown_name",
            path="design",
        )
    return plant


def load_plant(context, design, where):
    """Return a new gemini plant: the project's (``design`` None) or a stored ``design/<name>``.

    The project's plant is copied through its plant dict, so a run never changes the workspace's
    plant object.
    """
    import gemini as gm

    if design is None:
        return gm.Plant.from_dict(project_plant(context, where).to_dict(structure=True))
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


@tool(effect="read")
def read_plant(context, design: str | None = None, plant_class: str | None = None):
    """Read the project's plant, a stored design or a plant class: file, ranges, issues.

    Give ``design`` as ``design/<name>`` or ``plant_class`` as a name from
    ``list_plants``, not both; with neither, the project's plant is read (a project with several
    plant files needs one of the two). Returns ``plant`` (the plant file ``build_plant`` takes),
    ``ranges`` (each searchable leaf as ``{min, max}`` in display units), ``options`` and
    ``issues`` (what is wrong or missing, with path, kind, quantity and accepted units). With a
    case in the state the issues come from ``gm.check(plant, case)`` and ``checked_against`` is
    ``case``; without one they come from the plant alone (``plant``), which lists as missing
    what the case would fill. A class is read without values: every parameter it needs is
    missing until you fill it in a plant file.
    """
    import gemini as gm

    if design is not None and plant_class is not None:
        raise ToolError(
            "read_plant: design and plant_class are both given; expected one of them",
            path="design",
        )
    if plant_class is not None:
        plant = gm.plants.get(plant_class)
    else:
        plant = load_plant(context, design, "read_plant")
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

    built = await asyncio.to_thread(gm.Plant.from_dict, plant)
    design = await save_design(context, name, built)
    return {"design": design, **plant_issues(context, built)}


@tool(effect="write")
async def set_ranges(
    context,
    design: str,
    ranges: dict[str, dict[str, Any]],
    name: str,
    options: dict[str, list[Any]] | None = None,
):
    """Put search ranges and options on the leaves of a design; store it as design/<name>.

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
