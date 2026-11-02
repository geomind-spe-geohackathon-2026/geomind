"""The tools over gemini's module catalogue."""

from typing import Any

from geomind.tools.base import tool


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


def plain(found):
    """Return ``found`` with every gemini ``Quantity`` in it as its ``{value, unit}`` dict."""
    import gemini as gm

    if isinstance(found, dict):
        return {key: plain(value) for key, value in found.items()}
    if isinstance(found, gm.units.Quantity):
        return found.to_dict()
    return found


@tool(effect="compute")
def evaluate_module(
    name: str,
    parameters: dict[str, Any],
    inlets: dict[str, dict[str, Any]] | None = None,
    controls: dict[str, Any] | None = None,
    state: dict[str, Any] | None = None,
    dt: dict[str, Any] | None = None,
):
    """Run one module at one point in display units; every inlet needs a fluid.

    Give every value with a dimension as ``{"value": 150, "unit": "m3/h"}``, never as text such as
    '150 m3/h'. Every inlet needs ``fluid`` (a mapping such as ``{"kind": "brine"}``), ``T``, ``p``
    and ``m_dot`` (or ``flow`` for a volume flow). The result is in gemini's display units (MW,
    degC, m3/h; a quantity it has no display unit for stays in SI). A module with state needs
    ``state``, its state at the start as ``{name: {"value", "unit"}}``, and ``dt``, the step as
    ``{"value", "unit"}``; the ``state`` of the result is the state after the step.
    """
    import gemini as gm

    called = gm.call(
        gm.modules.get(name),
        parameters,
        inlets,
        controls,
        units="display",
        on_error="raise",
        state=state,
        dt=dt,
    )
    return plain(called)
