"""The tool that reads a skill."""

from geomind.context.skills import load_skill
from geomind.tools.base import tool


def role_of(context):
    """Return the ``<team>/<name>`` of the agent calling a tool, or ``None`` outside a run."""
    session = getattr(context, "_session", None) or getattr(context, "session", None)
    agent = getattr(session, "agent", None)
    return getattr(getattr(agent, "prompt", None), "role", None)


@tool(effect="read")
def read_skill(context, name: str):
    """Return the instructions of one skill, by its name in the system prompt.

    ``<skill>/<file>`` reads a file the skill names.
    """
    return load_skill(name, role_of(context))
