"""The tools that read and store plants."""

from typing import Any

from geomind.errors import NotImplementedYet
from geomind.tools.base import tool


def plant_schema():
    """Return gemini's plant schema, which ``build_plant`` offers as the input ``plant``."""
    import gemini as gm

    return gm.plants.spec_schema()


@tool(effect="read")
def list_plants():
    """List the registered plants, with their name and summary."""
    raise NotImplementedYet("list_plants comes in S2b")


@tool(effect="read")
def read_plant(context, design: str | None = None):
    """Describe a plant with its current values: the project's plant, or a stored design."""
    raise NotImplementedYet("read_plant comes in S2b")


@tool(effect="write", late_schemas={"plant": plant_schema})
def build_plant(context, plant: dict[str, Any], name: str):
    """Validate a plant and store it as design/<name>; a plant with problems is not stored."""
    raise NotImplementedYet("build_plant comes in S2b")
