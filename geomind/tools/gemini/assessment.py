"""The tools that judge a stored run with gemini: checks, KPIs and costs on its own case."""

from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.explain import explained
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.stored import load_run
from geomind.tools.gemini.verification import METRIC_EXCLUDED, assess, displayed
from geomind.utils.strings import did_you_mean, join_names

COSTS = (
    "capex",
    "opex",
    "annualised_cost",
    "lcoh",
    "lcoc",
    "lcts",
    "npv",
    "payback",
    "co2",
)
"""The costs of ``estimate_costs``, all functions of ``gm.evaluate``."""


@tool(effect="compute", late_schemas={"reference": reference_schema("result")})
def check_results(context, reference: str):
    """Check stored results against the case they ran on: gemini's verdict and report.

    Returns ``{feasible, reasons, requirements, failures, metrics}``, gemini's, in display units.
    ``feasible`` is ``gm.evaluate.verdict``, the one rule: true when nothing is wrong. ``reasons``
    says what is, each with a ``kind`` (``requirement``, ``failed_step``, ``numerical`` or
    ``bound``), a ``name`` and a ``message``. ``requirements`` is one check per unit of each
    requirement of the case and per service supply temperature, ``failures`` the failed and skipped
    steps by module and code, and ``metrics`` the energies, capacities, costs and CO2. A limit is a
    requirement of the case: set it with ``set_case``.
    """
    return assess(*load_run(context, reference, "check_results"))


def kpi_values(plant, case, results):
    """Return gemini's totals and the metrics of its report, ``{name: value in display units}``."""
    import gemini as gm

    report = gm.evaluate.report(plant, case, results)
    totals = displayed(report, gm.evaluate.totals(plant, case, results))
    metrics = {name: item for name, item in report.to_dict().items() if name not in METRIC_EXCLUDED}
    errors = cost_errors(plant, case, results, metrics)
    return {**totals, **metrics, **({"errors": errors} if errors else {})}


def cost_errors(plant, case, results, metrics):
    """Return ``{cost: error}`` of each cost gemini gave no value for: ``case_incomplete``, paths.

    NOTE: gemini's report gives only a ``reason`` text for such a cost, or leaves it out; the cost
    is asked of gemini once more, for those costs only, to get its error and the path in the case.
    The entries stay as the report gives them, so the shape of 0.4.11 holds.
    """
    missing = [name for name in COSTS if (metrics.get(name) or {}).get("value") is None]
    if not missing:
        return {}
    _, errors = cost_values(plant, case, results, missing)
    return {name: explained(errors[name]) for name in missing if name in errors}


@tool(effect="compute", late_schemas={"reference": reference_schema("result")})
def compute_kpis(context, reference: str, names: list[str] | None = None):
    """Compute KPIs of stored results in display units, all of them without ``names``.

    The KPIs are the totals of ``gm.evaluate.totals`` (what crossed the plant's edge, coverage,
    COP, peaks) and the metrics of ``gm.evaluate.report``. ``errors`` maps each cost gemini gives
    no value for to its error, ``case_incomplete`` with the path in the case when a value is
    missing; it is left out when there is none.
    """
    found = kpi_values(*load_run(context, reference, "compute_kpis"))
    for name in names or ():
        if name not in found:
            raise ToolError(
                f"compute_kpis: names = {name!r}; expected one of {join_names(found)}"
                f"{did_you_mean(name, found)}",
                code="unknown_name",
                path="names",
            )
    if not names:
        return found
    chosen = {name: found[name] for name in names}
    errors = {name: error for name, error in found.get("errors", {}).items() if name in names}
    return {**chosen, **({"errors": errors} if errors else {})}


def cost_values(plant, case, results, names=COSTS):
    """Return ``(values, errors)`` of gemini's costs: ``{name: Value}`` and ``{name: error}``."""
    import gemini as gm

    values, errors = {}, {}
    for name in names:
        arguments = (plant, case) if name == "capex" else (plant, case, results)
        try:
            values[name] = getattr(gm.evaluate, name)(*arguments)
        except gm.errors.ValidationError as error:
            errors[name] = error
    return values, errors


@tool(effect="compute", late_schemas={"reference": reference_schema("result")})
def estimate_costs(context, reference: str):
    """Estimate capex, opex, LCOH, LCOC, LCTS, NPV, payback, CO2 and the annualised cost.

    Every value is gemini's (``gm.evaluate``) on the run's case, in display units with its parts;
    prices, discount rate, analysis period and cost factors are the case's ``economics.json``.
    Nothing the file lacks is filled: a cost that needs it is ``{"error": {path, code, message}}``
    with gemini's error (its code and the path in the case), and when no cost can be computed the
    call fails with the first of them. Set the value in the case's economics or ask the user.
    """
    import gemini as gm

    plant, case, results = load_run(context, reference, "estimate_costs")
    values, errors = cost_values(plant, case, results)
    if not values:
        raise next(iter(errors.values()))
    shown = displayed(gm.evaluate.report(plant, case, results), values)
    return {
        name: shown[name] if name in shown else {"error": explained(errors[name])} for name in COSTS
    }
