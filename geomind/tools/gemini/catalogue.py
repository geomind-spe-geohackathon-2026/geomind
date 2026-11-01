"""The tools over gemini's module catalogue."""

from typing import Any

from geomind.tools.base import tool

READABLE_UNITS = {
    "pressure": "bar",
    "temperature": "degC",
    "power": "kW",
    "volume_flow": "m3/h",
}
"""The unit in which ``evaluate_module`` shows each quantity family; the others stay SI."""


@tool(effect="read")
def list_modules(category: str | None = None):
    """List the modules gemini has, with their name, category and summary."""
    import gemini as gm

    rows = []
    for name in gm.modules.names(category):
        description = gm.modules.get(name)().describe()
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

    return gm.modules.get(name)().describe()


@tool(effect="compute")
def evaluate_module(
    name: str,
    parameters: dict[str, Any],
    inlets: dict[str, dict[str, Any]] | None = None,
    controls: dict[str, Any] | None = None,
):
    """Run one module at one point and return its outlets and outputs in readable units.

    Give every value with a dimension as ``{"value": 150, "unit": "m3/h"}``, never as text such as
    '150 m3/h'. An inlet takes ``m_dot`` (or ``flow`` for a volume flow), ``T`` and ``p``.
    """
    import gemini as gm

    return gm.call(
        gm.modules.get(name), parameters, inlets, controls, on_error="raise", units=READABLE_UNITS
    )
