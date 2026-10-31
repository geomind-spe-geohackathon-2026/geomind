"""The tools over gemini's module catalogue."""

from typing import Any

from geomind.tools.base import tool


@tool(effect="read")
def list_modules(category: str | None = None):
    """List the modules gemini has, with their name, category and summary."""
    import gemini as gm

    rows = []
    for name in gm.modules.names(category):
        description = gm.modules.get(name).describe()
        rows.append(
            {
                "name": name,
                "category": description["category"],
                "summary": description["summary"],
            }
        )
    return rows


@tool(effect="read")
def describe_module(name: str):
    """Describe one module: its parameters, ports, outputs and children."""
    import gemini as gm

    return gm.modules.get(name).describe()


@tool(effect="compute")
def evaluate_module(
    name: str,
    parameters: dict[str, Any],
    inlets: dict[str, dict[str, Any]] | None = None,
    controls: dict[str, Any] | None = None,
):
    """Run one module at one point; numbers may be SI or text such as '150 m3/h'."""
    import gemini as gm

    return gm.evaluate(gm.modules.get(name), parameters, inlets, controls)
