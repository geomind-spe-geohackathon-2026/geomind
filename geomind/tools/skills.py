"""The tool that reads a skill."""

from geomind.context.skills import load_skill
from geomind.tools.base import tool


@tool(effect="read")
def read_skill(name: str):
    """Return the instructions of one skill, by its name in the system prompt."""
    return load_skill(name)
