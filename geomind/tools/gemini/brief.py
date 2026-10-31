"""A brief in gemini's terms: the rules of ``gm.schedule`` and the amounts of verification.

Every number comes from a ``Brief`` (``geomind/context/brief.py``), the state's or a preset's; this
module holds none of a brief's numbers. ``gm.units`` parses and converts every amount.
"""

from typing import Any

from pydantic import ValidationError

from geomind.context import preset, with_changes
from geomind.errors import ToolError
from geomind.tools.base import tool

ORDER = ["geothermal", "heat_pump", "boiler"]
"""The order ``gm.schedule`` asks the heat sources in; a brief gives none, so it is the default."""

FALLBACK = "hackathon_2027"
"""The preset a tool uses when the state has no brief, as every tool did before briefs were data."""

TOLERANCE = {"temperature": 1e-3, "power": 1e-3, "volume_flow": 1e-9}
"""The one numerical tolerance of verification, in SI (K, W, m3/s), by quantity.

NOTE: it only absorbs floating-point noise, such as an unmet demand of 3e-8 W on a day that is fully
met; it never relaxes a limit of the brief.
"""

RESERVOIR = {
    "depth": "length",
    "thickness": "length",
    "gradient": "temperature_gradient",
    "surface_temperature": "temperature",
    "pressure": "pressure",
    "permeability": "permeability",
    "density": "density",
    "viscosity": "viscosity",
    "gas_liquid_ratio": "gas_liquid_ratio",
}
"""The gemini quantity of each reservoir and brine amount of a brief."""


def text(amount):
    """Return an amount as gemini parses it: ``"<number> <unit>"``."""
    if isinstance(amount, dict):
        return f"{amount['value']} {amount['unit']}"
    return amount


def si(amount, unit):
    """Return the number of an amount in ``unit``, through ``gm.units``."""
    import gemini as gm

    value, given = gm.units.parse(text(amount))
    return gm.units.convert(value, given, unit)


def brief_of(context):
    """Return ``(brief, source)``: the state's brief, or the fallback preset when it has none.

    ``source`` says which, for the summaries of the tools: a run never takes the hackathon's
    numbers without saying so.
    """
    problem = getattr(context, "problem", None)
    brief = problem.brief if problem is not None else None
    if brief is not None:
        return brief, f"the state's brief ({brief.source or 'no source'})"
    return preset(FALLBACK), f"no brief in the state: the {FALLBACK} preset"


def schedule_rules(brief, where="simulate"):
    """Return the rules of ``gm.schedule`` from a brief; a rule it needs and lacks raises.

    NOTE: ``operating_days`` stays ``None``: ``gm.schedule`` raises ``NotImplementedYet`` for any
    other value until gemini decides what the "330 daily steps" mean, so every doublet runs every
    day, and verification lists the brief's operating days as blocked.
    """
    flow = brief.doublet_flow
    missing = [
        name
        for name, value in (
            ("doublet_flow.min", flow.min if flow else None),
            ("doublet_flow.max", flow.max if flow else None),
            ("max_brine_cooling", brief.max_brine_cooling),
        )
        if value is None
    ]
    if missing:
        raise ToolError(
            f"{where}: brief = {', '.join(missing)} not given; expected them, since gm.schedule "
            "plans each doublet's flow with them. Set them with set_brief or ask the user",
            path="brief",
        )
    return {
        "order": list(ORDER),
        "doublet_flow": {"min": text(flow.min), "max": text(flow.max)},
        "max_brine_cooling": text(brief.max_brine_cooling),
        "operating_days": None,
    }


def field(record, name):
    """Return a field of an optional record."""
    return getattr(record, name) if record is not None else None


def amounts(brief):
    """Return ``(path, quantity, amount)`` of every amount a brief gives, by gemini quantity."""
    found = [
        *(
            (f"doublet_flow.{end}", "volume_flow", field(brief.doublet_flow, end))
            for end in ("min", "max")
        ),
        ("max_brine_cooling", "temperature_difference", brief.max_brine_cooling),
        ("pump_efficiency", "efficiency", brief.pump_efficiency),
        *(
            (f"{network}.{name}", "temperature", field(getattr(brief, network), name))
            for network in ("heating", "cooling")
            for name in ("supply", "return_temperature")
        ),
        *(
            (f"reservoir.{name}", quantity, field(brief.reservoir, name))
            for name, quantity in RESERVOIR.items()
        ),
    ]
    return [item for item in found if item[2] is not None]


def amount_problems(brief):
    """Return one line per amount of a brief that ``gm.units`` cannot read as its quantity."""
    import gemini as gm

    problems = []
    for path, quantity, amount in amounts(brief):
        try:
            _, unit = gm.units.parse(text(amount))
        except gm.errors.ValidationError as error:
            problems.append(f"{path} = {amount!r}: {error}")
            continue
        if not gm.units.fits(unit, quantity):
            problems.append(f"{path} = {amount!r}: expected a unit of {quantity}")
    return problems


def problems_of(error):
    """Return the validation errors of a brief as one line."""
    return "; ".join(f"{'.'.join(map(str, item['loc']))}: {item['msg']}" for item in error.errors())


def new_brief(context, name, changes):
    """Return the brief ``set_brief`` writes: a preset or the state's brief, with ``changes``.

    A brief with changes is the user's unless ``changes`` names its source.
    """
    base = preset(name) if name else context.problem.brief
    try:
        brief = with_changes(base, changes or {})
    except ValidationError as error:
        raise ToolError(f"set_brief: changes: {problems_of(error)}", path="changes") from None
    problems = amount_problems(brief)
    if problems:
        raise ToolError(f"set_brief: {'; '.join(problems)}", path="changes")
    if changes and "source" not in changes:
        return brief.model_copy(update={"source": "user"})
    return brief


@tool(effect="write", idempotent=False, reruns_in_replay=True)
async def set_brief(context, preset: str | None = None, changes: dict[str, Any] | None = None):
    """Set the brief of the problem state: a named preset, the values the user gave, or both.

    ``preset`` loads a named brief (``hackathon_2027``) and ``changes`` replaces fields of it, or
    of the state's brief without a preset, as the JSON of a partial brief: ``demand`` {heating,
    cooling} profile names; ``doublets`` {min, max}; ``doublet_flow`` {min, max};
    ``max_brine_cooling``; ``operating_days``; ``pump_efficiency``; ``volume_balance``;
    ``heating`` and ``cooling`` {supply, return_temperature}; ``reservoir`` {depth, thickness,
    gradient, surface_temperature, pressure, permeability, density, viscosity,
    gas_liquid_ratio, gas_composition}; ``source`` (user or agent). Amounts are texts such as
    ``"300 m3/h"``; a field set to null is not given. Returns the brief and the state version.
    """
    brief = new_brief(context, preset, changes)
    value = brief.model_dump(mode="json")
    version = await context.session.change_state(
        [{"op": "replace", "path": "/brief", "value": value}]
    )
    return {"brief": brief.model_dump(mode="json", exclude_none=True), "version": version}
