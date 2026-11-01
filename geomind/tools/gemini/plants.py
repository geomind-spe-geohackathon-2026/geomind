"""The tools that read and store plants."""

import asyncio
from typing import Any

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.stored import DESIGN, load_design, save_design


def plant_schema():
    """Return gemini's plant schema, which ``build_plant`` offers as the input ``plant``."""
    import gemini as gm

    return gm.plants.schema()


@tool(effect="read")
def list_plants():
    """List the plant classes with their summary, and what each can do.

    ``capabilities`` maps a class to its ``roles``, whether it is ``schedulable`` and its
    ``choices``, the structural sizes a design may choose.
    """
    import gemini as gm

    return {
        "plants": [
            {"name": name, "summary": gm.plants.get(name).describe()["summary"]}
            for name in gm.plants.names()
        ],
        "capabilities": gm.plants.capabilities(),
    }


def project_plant(context, where):
    """Return the plant of the run's project, or raise a result the model can act on."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError(
            f"{where}: this run has no project; expected a workspace and one, or a design",
            code="not_allowed",
        )
    plant = workspace.plant(context.project)
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


@tool(effect="read")
def read_plant(context, design: str | None = None):
    """Read a plant: the project's, a stored design ``design/<name>`` or a plant class by name.

    The result has ``plant``, the plant dict ``build_plant`` takes, and ``missing_parameters``, the
    values still to set, each with its path, quantity, unit, limits and description. A class is
    read without values, so every parameter it needs is missing: fill them in a plant dict.
    """
    import gemini as gm

    if design is None or design.startswith(DESIGN):
        plant = load_plant(context, design, "read_plant")
    else:
        plant = gm.plants.get(design)
    return {
        "plant": plant.to_dict(structure=True),
        "missing_parameters": plant.missing_parameters(),
    }


@tool(effect="write", late_schemas={"plant": plant_schema})
async def build_plant(context, plant: dict[str, Any], name: str):
    """Validate a plant dict and store it as design/<name>; a plant with problems is not stored.

    The problems are gemini's, each with the ``path`` of the fault, a ``code`` and ``suggestions``
    such as the name that was probably meant.
    """
    import gemini as gm

    problems = await asyncio.to_thread(gm.plants.validate, plant, on_error="record")
    if problems:
        return {"design": None, "problems": problems}
    design = await save_design(context, name, gm.Plant.from_dict(plant))
    return {"design": design, "problems": []}
