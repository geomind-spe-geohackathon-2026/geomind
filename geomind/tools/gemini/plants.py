"""The tools that read and store plants."""

import asyncio
import re
from typing import Any

from geomind.errors import ToolError
from geomind.tools.base import tool

DESIGN = "design/"
EXAMPLE = "example/"
TEMPLATE = "template/"
DESIGN_NAME = re.compile(r"[A-Za-z0-9._-]+")


def plant_schema():
    """Return gemini's plant schema, which ``build_plant`` offers as the input ``plant``."""
    import gemini as gm

    return gm.plants.spec_schema()


@tool(effect="read")
def list_plants():
    """List the registered plants, with their name and summary."""
    import gemini as gm

    return [
        {"name": name, "summary": gm.plants.get(name).describe()["summary"]}
        for name in gm.plants.names()
    ]


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


def stored_design(context, design, where):
    """Return the spec stored under a design reference, or raise ``unknown_name``."""
    spec = context.session.load_artifact(design) if design.startswith(DESIGN) else None
    if spec is None:
        raise ToolError(
            f"{where}: design = {design!r}; expected a reference that build_plant returned,"
            " such as 'design/<name>'",
            code="unknown_name",
            path="design",
        )
    return spec


def apply_inputs(plant, spec):
    """Set the inputs a spec keeps in ``boundary[""]["inputs"]``, by module path and name.

    NOTE: a bridge until gemini reads them itself. Setpoints such as a heat pump's
    ``temperature_setpoint`` can be set only through ``plant.set_inputs``, which ``api.md`` does not
    list and ``to_dict`` does not keep, while ``gm.schedule`` and ``gm.simulate`` need them. The
    spec's ``boundary`` validates and round-trips them, so a design stores them there and this one
    call applies them. It is item 13 of the gemini requests.
    """
    stored = (spec.get("boundary") or {}).get("", {}).get("inputs") or {}
    inputs = {
        f"{path}.{name}" if path else name: value
        for path, values in stored.items()
        for name, value in values.items()
    }
    if inputs:
        plant.set_inputs(inputs)
    return plant


def plant_spec(context, design, where):
    """Return the spec of a plant: the project's, a stored design, an example or a template.

    ``example/<Name>`` is ``gm.plants.example`` and ``template/<name>`` is
    ``gm.plants.from_template``; both are read-only starts for a design.
    """
    import gemini as gm

    if design is None:
        return project_plant(context, where).to_dict()
    if design.startswith(EXAMPLE):
        return gm.plants.example(design.removeprefix(EXAMPLE)).to_dict()
    if design.startswith(TEMPLATE):
        return gm.plants.from_template(design.removeprefix(TEMPLATE)).to_dict()
    return stored_design(context, design, where)


def load_plant(context, design, where):
    """Return a new gemini plant from ``plant_spec``, its stored inputs applied.

    NOTE: the project's plant goes through its spec too, so a run never changes the workspace's
    plant object.
    """
    import gemini as gm

    spec = plant_spec(context, design, where)
    return apply_inputs(gm.plants.from_dict(spec), spec)


@tool(effect="read")
def read_plant(context, design: str | None = None):
    """Describe a plant with its current values: the project's plant, or a stored design.

    ``design`` may also be ``example/<Name>`` or ``template/<name>``, read-only starts for a design.
    The result is gemini's ``describe()`` with the plant's spec under ``spec``, the plant file
    ``build_plant`` takes, so a design is built from an edited copy.
    """
    import gemini as gm

    spec = plant_spec(context, design, "read_plant")
    return {**apply_inputs(gm.plants.from_dict(spec), spec).describe(), "spec": spec}


@tool(effect="write", late_schemas={"plant": plant_schema})
async def build_plant(context, plant: dict[str, Any], name: str):
    """Validate a plant and store it as design/<name>; a plant with problems is not stored."""
    import gemini as gm

    if not DESIGN_NAME.fullmatch(name) or set(name) == {"."}:
        raise ToolError(
            f"build_plant: name = {name!r}; expected letters, digits, '.', '_' or '-'",
            path="name",
        )
    problems = await asyncio.to_thread(gm.plants.validate, plant, on_error="record")
    if problems:
        return {"design": None, "problems": problems}
    await context.session.save_artifact(f"{DESIGN}{name}", plant)
    return {"design": f"{DESIGN}{name}", "problems": []}
