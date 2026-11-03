"""The tools over gemini's module catalogue."""

import difflib
from typing import Any

from geomind.errors import ToolError
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
    """Describe one module compactly: parameters and controls one per line, ports and outputs.

    A line gives the type, quantity and units, bounds and options, with * when no default.
    """
    import gemini as gm

    from geomind.tools.gemini.skeleton import module_tree

    return module_tree(gm.modules.get(name)().describe())


def checked_names(name, description, parameters, controls):
    """Raise ``invalid_input`` for a parameter or control the module does not have.

    gemini raises a bare ``KeyError`` for a control given as a parameter
    (``temperature_setpoint`` of a heat pump); the energy engineer saw ``internal`` three times
    and could not fix it (#76).
    """
    owned = {"parameters": set(description["parameters"]), "controls": set(description["controls"])}
    given = {"parameters": set(parameters or {}), "controls": set(controls or {})}
    for kind, other in (("parameters", "controls"), ("controls", "parameters")):
        for key in sorted(given[kind] - owned[kind]):
            where = (
                f"; it is a {other[:-1]} of {name}: give it in `{other}`"
                if key in owned[other]
                else f"; expected one of {', '.join(sorted(owned[kind])) or 'none'}"
            )
            raise ToolError(
                f"evaluate_module: {kind}.{key} is not a {kind[:-1]} of {name}{where}",
                code="invalid_input",
                path=f"{kind}.{key}",
                suggestions=difflib.get_close_matches(key, sorted(owned[kind] | owned[other])),
            )


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
    '150 m3/h'. Every inlet is ``{"fluid": {...}, "T": {...}, "p": {...}, "m_dot": {...}}`` (or
    ``flow`` for a volume flow), for example ``{"fluid_in": {"fluid": {"kind": "brine",
    "density": {"value": 1000, "unit": "kg/m3"}}, "T": {"value": 80, "unit": "degC"},
    "p": {"value": 10, "unit": "bar"}, "flow": {"value": 100, "unit": "m3/h"}}}``. ``fluid``
    holds gemini's fluid fields: ``kind`` (brine, water, glycol_water, steam, gas), ``salinity``,
    ``gas_liquid_ratio``, ``gas_composition`` and the properties ``density``, ``viscosity``,
    ``specific_heat``, each property as ``{"value", "unit"}``; ``kind`` alone uses gemini's. The
    result is in gemini's display units (MW, degC, m3/h; a quantity it has no display unit for
    stays in SI). A module with state needs
    ``state``, its state at the start as ``{name: {"value", "unit"}}``, and ``dt``, the step as
    ``{"value", "unit"}``; the ``state`` of the result is the state after the step.
    """
    import gemini as gm

    checked_names(name, gm.modules.get(name)().describe(), parameters, controls)
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
