"""The tools over gemini's module catalogue."""

from typing import Any

from geomind.errors import NotImplementedYet
from geomind.tools.base import tool


@tool(effect="read")
def list_modules(category: str | None = None):
    """List the modules gemini has, with their name, category and summary."""
    raise NotImplementedYet("list_modules comes in S2b")


@tool(effect="read")
def describe_module(name: str):
    """Describe one module: its parameters, ports, outputs and children."""
    raise NotImplementedYet("describe_module comes in S2b")


@tool(effect="compute")
def evaluate_module(
    name: str,
    parameters: dict[str, Any],
    inlets: dict[str, dict[str, Any]] | None = None,
    controls: dict[str, Any] | None = None,
):
    """Run one module at one point; numbers may be SI or text such as '150 m3/h'."""
    raise NotImplementedYet("evaluate_module comes in S2b")
