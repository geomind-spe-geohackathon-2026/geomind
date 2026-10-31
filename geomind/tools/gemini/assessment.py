"""The tools that judge a design: checks, KPIs, costs, optimisation and agent-written modules."""

from typing import Any

from geomind.errors import NotImplementedYet
from geomind.tools.base import tool


@tool(effect="compute")
def check_results(context, reference: str, limits: dict[str, Any] | None = None):
    """Check stored results: energy and mass balances, limits and the hard limits."""
    raise NotImplementedYet("check_results comes in S3")


@tool(effect="compute")
def compute_kpis(context, reference: str, names: list[str] | None = None):
    """Compute KPIs of stored results, all of them without ``names``."""
    raise NotImplementedYet("compute_kpis comes in S3")


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
