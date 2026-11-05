"""The tools that judge a stored run with gemini: checks, KPIs and costs on its own case."""

import json

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

COST_NAMES = (*COSTS, "costs")
"""The names an agent may ask ``compute_kpis`` for that are costs: ``estimate_costs`` has them
(QA-209)."""


@tool(effect="compute", late_schemas={"reference": reference_schema("result")})
def check_results(context, reference: str):
    """Check stored results against the case they ran on: gemini's verdict and report.

    Skill `reading-results`.
    """
    return assess(*load_run(context, reference, "check_results"))


def kpi_values(plant, case, results):
    """Return gemini's totals and the metrics of its report, ``{name: value in display units}``.

    The split of each service by source (``coverage_split``) comes with them, so that no agent
    derives the geothermal heat by subtraction (QA-228).
    """
    import gemini as gm

    report = gm.evaluate.report(plant, case, results)
    totals = displayed(report, gm.evaluate.totals(plant, case, results))
    split = displayed(report, coverage_split(plant, case, results))
    metrics = {name: item for name, item in report.to_dict().items() if name not in METRIC_EXCLUDED}
    errors = cost_errors(plant, case, results, metrics)
    return {**totals, **split, **metrics, **({"errors": errors} if errors else {})}


SPLIT = {"heating": "heat", "cooling": "cold"}
"""The word of each service in the names of ``coverage_split``."""


def coverage_split(plant, case, results):
    """Return what covered each service over the run: geothermal, backup and unmet, and the share.

    Summed from gemini's ``daily_coverage``, the figures the Results page shows: for heating
    ``geothermal_heat``, ``backup_heat`` (the boilers, the CHP and an electric boiler),
    ``unmet_heat`` [J] and ``geothermal_heat_share`` (geothermal over the demand, -); the same
    with ``cold`` for cooling, where a compression chiller is backup. With gemini 0.6.22 the heat
    pumps' compressor work is ``heat_pump_electricity`` and ``geothermal_heat`` the brine's heat
    alone (QA-270). A service the plant has no consumer for is left out.
    """
    import gemini as gm

    found = {}
    for service, days in gm.evaluate.daily_coverage(plant, case, results).items():
        word = SPLIT[service]
        keys = ("demand", "geothermal", "electricity", "backup", "short")
        sums = {key: sum(day[key].si for day in days if key in day) for key in keys}
        found[f"geothermal_{word}"] = gm.units.Quantity(sums["geothermal"], "J")
        if service == "heating" and any("electricity" in day for day in days):
            found["heat_pump_electricity"] = gm.units.Quantity(sums["electricity"], "J")
        found[f"backup_{word}"] = gm.units.Quantity(sums["backup"], "J")
        found[f"unmet_{word}"] = gm.units.Quantity(sums["short"], "J")
        share = sums["geothermal"] / sums["demand"] if sums["demand"] > 0 else None
        found[f"geothermal_{word}_share"] = gm.units.Quantity(share, "-")
    return found


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
    return gap_problems(plant, case, results, errors)


def gap_problems(plant, case, results, errors):
    """Return ``{cost: problem}``; a case gap lists every value gemini says the costs need.

    NOTE: ``gm.evaluate.missing`` asks all the costs at once, so each ``case_incomplete`` has the
    same, full list in ``suggestions`` instead of the first value of its own metric only.
    """
    import gemini as gm

    problems = {name: explained(error) for name, error in errors.items()}
    if not any(problem["code"] == "case_incomplete" for problem in problems.values()):
        return problems
    gaps = [issue.problem()["path"] for issue in gm.evaluate.missing(plant, case, results)]
    return {
        name: (
            {**problem, "suggestions": gaps}
            if problem["code"] == "case_incomplete" and gaps
            else problem
        )
        for name, problem in problems.items()
    }


@tool(effect="compute", late_schemas={"reference": reference_schema("result")})
def compute_kpis(context, reference: str, names: list[str] | None = None):
    """Compute KPIs of stored results in display units, all of them without ``names``.

    Skill `economics`.
    """
    found = kpi_values(*load_run(context, reference, "compute_kpis"))
    for name in names or ():
        if name not in found and name in COST_NAMES:
            raise ToolError(
                f"compute_kpis: names = {list(names)}: {name} is a cost metric, which compute_kpis"
                " does not have; costs (lcts, lcoh, lcoc, capex, opex, annualised_cost) come from"
                f" estimate_costs, or from read_study for a study's metrics. Its names:"
                f" {join_names(found)}",
                code="unknown_name",
                path="names",
            )
        if name not in found:
            raise ToolError(
                f"compute_kpis: names = {name!r}; expected one of {join_names(found)}"
                f"{did_you_mean(name, found)}",
                code="unknown_name",
                path="names",
            )
    if not names:
        return rounded(found)
    chosen = {name: found[name] for name in names}
    errors = {name: error for name, error in found.get("errors", {}).items() if name in names}
    return rounded({**chosen, **({"errors": errors} if errors else {})})


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

    Skill `economics`.
    """
    import gemini as gm

    plant, case, results = load_run(context, reference, "estimate_costs")
    values, errors = cost_values(plant, case, results)
    problems = gap_problems(plant, case, results, errors)
    if not values:
        first = next(iter(problems.values()))
        raise ToolError(
            first["message"],
            code=first["code"],
            path=first["path"],
            suggestions=first["suggestions"],
        )
    shown = displayed(gm.evaluate.report(plant, case, results), values)
    costs = {name: shown[name] if name in shown else {"error": problems[name]} for name in COSTS}
    return rounded({**costs, "economics": economics_used(context, reference)})


def economics_used(context, reference):
    """Return whether the costs used the economics of the state's case, and what differs (QA-258).

    The costs of a stored result are those of the case its run ran on. After a ``set_case`` that
    changed the economics, the same result gives the same costs; an economist costed the old
    result four times to find the new prices. The answer says it at once: ``same_as_case`` and,
    when it is false, the ``changed`` keys and the call that gives the new costs.
    """
    from geomind.tools.gemini.case import file_contents, state_case
    from geomind.tools.gemini.stored import RESULT, run_files, unquoted

    identifier = unquoted(reference).removeprefix(RESULT)
    ran = context.session.load_artifact(f"{identifier}.case") if identifier else None
    try:
        current = state_case(context)
    except ToolError:
        current = None
    if not isinstance(ran, dict) or current is None:
        return {"same_as_case": None, "note": "the case of this result's run is not known here"}
    changed = changed_keys(
        sheet(ran.get("economics"), lambda: run_files(context, identifier)),
        sheet(current.get("economics"), lambda: file_contents(context, current, {})),
    )
    if not changed:
        return {"same_as_case": True, "note": "the costs use the economics of the current case"}
    return {
        "same_as_case": False,
        "changed": changed,
        "note": (
            "these are the costs of the economics the run ran on, not of the current case: "
            "simulate the same plant again on the current case, then estimate_costs on that new "
            "result; costing this result again gives the same numbers"
        ),
    }


def sheet(economics, files):
    """Return the economics dict of a case's ``economics``: a dict, or a file's content read.

    A case may name its economics as a file (``"economics.json"``) and the same values may be a
    dict in the other case (QA-275): the two are compared by content. ``files`` gives
    ``{name: bytes}`` when called; a file that cannot be read keeps its name.
    """
    if not isinstance(economics, str):
        return economics
    try:
        content = files().get(economics)
        return json.loads(content) if content is not None else economics
    except (ToolError, OSError, ValueError):
        return economics


def changed_keys(old, new, prefix="economics"):
    """Return the dotted keys whose values differ between two economics values.

    The economics is a dict or the name of a case file; two values that are not both dicts differ
    as a whole.
    """
    if not (isinstance(old, dict) and isinstance(new, dict)) or "value" in new:
        return [] if old == new else [prefix]
    found = []
    for key in sorted(set(old) | set(new)):
        found += changed_keys(old.get(key), new.get(key), f"{prefix}.{key}")
    return found


SIGNIFICANT = 5
"""Significant digits of a figure the cost tools give: 23.956 MEUR, not 23.955885571022524."""


def rounded(found):
    """Return ``found`` with every float ``value`` to ``SIGNIFICANT`` digits (QA-099).

    The answers quoted 15 to 17 digits, a wall of numbers; five digits keep every figure the
    economics can support. Values in lists and nested maps are rounded the same way.
    """
    if isinstance(found, dict):
        return {
            key: (
                float(f"{item:.{SIGNIFICANT}g}")
                if key == "value" and isinstance(item, float)
                else rounded(item)
            )
            for key, item in found.items()
        }
    if isinstance(found, list):
        return [rounded(item) for item in found]
    return found
