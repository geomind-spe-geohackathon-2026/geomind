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


@tool(effect="compute")
def estimate_costs(context, reference: str, assumptions: dict[str, Any] | None = None):
    """Estimate capex, opex, LCOH, LCOC, NPV and CO2, and return the assumptions used."""
    raise NotImplementedYet("estimate_costs comes in S3")


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
