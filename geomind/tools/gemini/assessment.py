"""The tools that judge a design: checks, KPIs, costs, optimisation and agent-written modules."""

from typing import Any

from geomind.errors import NotImplementedYet, ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.plants import apply_inputs
from geomind.tools.gemini.verification import assess
from geomind.utils.strings import did_you_mean, join_names

RESULT = "result/"


def stored_run(context, reference, where):
    """Return the plant and the ``Results`` that ``simulate`` kept beside a result reference."""
    import gemini as gm

    identifier = reference.removeprefix(RESULT) if reference.startswith(RESULT) else None
    spec = context.session.load_artifact(f"{identifier}.plant") if identifier else None
    data = context.session.load_artifact(f"{identifier}.results") if identifier else None
    if spec is None or data is None:
        raise ToolError(
            f"{where}: reference = {reference!r}; expected a reference that simulate returned",
            code="unknown_name",
            path="reference",
        )
    return apply_inputs(gm.plants.from_dict(spec), spec), gm.Results.from_bytes(data)


@tool(effect="compute")
def check_results(context, reference: str, limits: dict[str, Any] | None = None):
    """Check stored results: energy and mass balances, limits and the hard limits.

    Returns ``{passed, checks, failures, not_assessed}``: gemini's checks with the brief's hard
    limits always among them, the domain of each failed check, and what gemini cannot judge yet.
    ``limits`` (what ``gm.checks.Limits.to_dict`` returns) are checked beside the brief's.
    """
    return assess(*stored_run(context, reference, "check_results"), limits)


def kpis(plant, results):
    """Return gemini's KPIs and plant totals of a run, ``{name: Value}``."""
    import gemini as gm

    return {**gm.kpi.compute(plant, results), **gm.kpi.totals(plant, results)}


@tool(effect="compute")
def compute_kpis(context, reference: str, names: list[str] | None = None):
    """Compute KPIs of stored results, all of them without ``names``.

    The KPIs are ``gm.kpi.compute`` and the plant totals of ``gm.kpi.totals``, each a Value.
    """
    found = kpis(*stored_run(context, reference, "compute_kpis"))
    for name in names or ():
        if name not in found:
            raise ToolError(
                f"compute_kpis: names = {name!r}; expected one of {join_names(found)}"
                f"{did_you_mean(name, found)}",
                code="unknown_name",
                path="names",
            )
    return {name: found[name] for name in names} if names else found


def energy_share(plant, results):
    """Return the heat's share of the energy delivered, from the totals of ``gm.kpi.totals``."""
    import gemini as gm

    totals = gm.kpi.totals(plant, results)
    heat, cold = totals["heat_delivered"]["value"], totals["cold_delivered"]["value"]
    if not heat or cold is None:
        raise ToolError(
            "estimate_costs: heat_cost_share = 'energy'; expected a run that delivers heat",
            path="assumptions.heat_cost_share",
        )
    return heat / (heat + cold)


def build_assumptions(values, plant, results):
    """Return ``gm.economics.Assumptions`` of the given values, or a result the model can fix."""
    import gemini as gm
    import pydantic

    known = gm.economics.Assumptions.model_fields
    for name in values:
        if name not in known:
            raise ToolError(
                f"estimate_costs: assumptions.{name}; expected one of {join_names(known)}"
                f"{did_you_mean(name, known)}",
                code="unknown_name",
                path=f"assumptions.{name}",
            )
    if values.get("heat_cost_share") == "energy":
        values = {**values, "heat_cost_share": energy_share(plant, results)}
    try:
        return gm.economics.Assumptions(**values)
    except pydantic.ValidationError as error:
        first = error.errors()[0]
        field = ".".join(str(part) for part in first["loc"])
        raise ToolError(
            f"estimate_costs: assumptions.{field}: {first['msg']}", path=f"assumptions.{field}"
        ) from None


def lcts(plant, results, assumptions):
    """Return the levelised cost of thermal service, a Value with its parts.

    LCTS = annualised total system cost / (annual heat delivered + annual cold delivered). NOTE:
    every number is gemini's: with ``heat_cost_share = 1`` the whole cost goes to the heat, so
    ``lcoh × energy`` of ``gm.economics.lcoh`` is the annualised total cost ``capex / A + opex``,
    and ``energy`` of ``lcoh`` and ``lcoc`` are the annual heat and cold. geomind only divides.
    """
    import gemini as gm

    whole = assumptions.model_copy(update={"heat_cost_share": 1.0})
    heat = gm.economics.lcoh(plant, results, assumptions=whole, on_error="record")
    cold = gm.economics.lcoc(plant, results, assumptions=whole, on_error="record")
    if heat["value"] is None:
        return {"value": None, "unit": heat["unit"], "reason": heat["reason"]}
    heat_energy = heat["energy"]["value"]
    cold_energy = (cold.get("energy") or {}).get("value") or 0.0
    annual = heat["value"] * heat_energy
    return {
        "value": annual / (heat_energy + cold_energy),
        "unit": heat["unit"],
        "annualised_cost": {"value": annual, "unit": f"{assumptions.currency}/year"},
        "heat": heat["energy"],
        "cold": cold.get("energy") or {"value": 0.0, "unit": heat["energy"]["unit"]},
    }


@tool(effect="compute")
def estimate_costs(context, reference: str, assumptions: dict[str, Any] | None = None):
    """Estimate capex, opex, LCOH, LCOC, NPV and CO2, and return the assumptions used.

    Every value is gemini's (``gm.economics`` with ``on_error="record"``), so a missing assumption
    is a null value with its reason. ``assumptions`` are fields of ``gm.economics.Assumptions``;
    ``heat_cost_share = "energy"`` splits the cost by the heat and cold delivered. ``lcts`` is the
    levelised cost of heating and cooling together.
    """
    import gemini as gm

    plant, results = stored_run(context, reference, "estimate_costs")
    used = build_assumptions(dict(assumptions or {}), plant, results)
    economics = gm.economics
    return {
        "capex": economics.capex(plant, used, on_error="record"),
        "opex": economics.opex(plant, results, used, on_error="record"),
        "lcoh": economics.lcoh(plant, results, assumptions=used, on_error="record"),
        "lcoc": economics.lcoc(plant, results, assumptions=used, on_error="record"),
        "npv": economics.npv(plant, results, assumptions=used, on_error="record"),
        "co2": economics.co2(plant, results, used, on_error="record"),
        "lcts": lcts(plant, results, used),
        "assumptions": used.model_dump(mode="json"),
    }


@tool(effect="compute")
def optimize(
    context,
    design: str,
    variables: dict[str, Any],
    objective: str,
    constraints: dict[str, Any] | None = None,
    budget: int | None = None,
):
    """Optimise a stored design and return the best design, its objective and the history."""
    raise NotImplementedYet("optimize comes in S4")


@tool(effect="compute")
def sample_uncertainty(
    context, design: str, distributions: dict[str, Any], samples: int, metrics: list[str]
):
    """Sample a stored design over its uncertain inputs; return P10, P50 and P90 per metric."""
    raise NotImplementedYet("sample_uncertainty comes in S4")


@tool(effect="execute")
def test_module(context, path: str):
    """Check an agent-written module file in the sandbox and return gemini's report."""
    raise NotImplementedYet("test_module comes in S3")
