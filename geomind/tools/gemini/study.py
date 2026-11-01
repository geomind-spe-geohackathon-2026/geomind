"""The tools that size, search, sample and compare stored designs, over the state's case."""

import asyncio
from typing import Any, Literal

from geomind.tools.base import tool
from geomind.tools.gemini.case import case_of
from geomind.tools.gemini.stored import load_design, load_run, save_design


def to_quantities(node):
    """Return ``node`` with every ``{"value", "unit"}`` dict made a ``gm.units.Quantity``."""
    import gemini as gm

    if isinstance(node, dict) and set(node) == {"value", "unit"}:
        return gm.units.Quantity(node["value"], node["unit"])
    if isinstance(node, dict):
        return {key: to_quantities(item) for key, item in node.items()}
    if isinstance(node, list):
        return [to_quantities(item) for item in node]
    return node


def to_plain(node):
    """Return ``node`` as JSON data: every ``Quantity`` as its ``{value, unit}`` dict."""
    import gemini as gm

    if isinstance(node, gm.units.Quantity):
        return node.to_dict()
    if isinstance(node, dict):
        return {key: to_plain(item) for key, item in node.items()}
    if isinstance(node, (list, tuple)):
        return [to_plain(item) for item in node]
    return node


def size_design(plant, case, backup):
    """Return the plant sized under the backup policy."""
    import gemini as gm

    return gm.study.size(plant, case, backup=backup)


@tool(effect="compute")
async def size_plant(context, design: str, backup: Literal["peak", "none"], name: str):
    """Size a stored design for the state's case and store the sized plant as design ``name``.

    ``backup`` is the policy for the boiler: ``peak`` covers the whole heating peak with the
    doublets off, ``none`` covers only what the doublets cannot reach. Returns the new design
    reference and gemini's notes: what was ``sized`` with its reason, what stayed ``unchanged``,
    what is ``broken`` and the ``simulation`` that judged it.
    """
    plant = load_design(context, design, "size_plant")
    case = case_of(context)
    sized = await asyncio.to_thread(size_design, plant, case, backup)
    reference = await save_design(context, name, sized)
    return {"design": reference, "sizing": to_plain(sized.sizing)}


def minimize_design(plant, case, objective, variables, constraints, evaluations):
    """Return gemini's search of the plant over the variables."""
    import gemini as gm

    return gm.study.minimize(
        plant,
        case,
        objective,
        to_quantities(variables) or None,
        to_quantities(constraints),
        evaluations,
    )


@tool(effect="compute")
async def optimize(
    context,
    design: str,
    objective: str,
    variables: list[dict[str, Any]],
    evaluations: int,
    name: str,
    constraints: list[dict[str, Any]] | None = None,
):
    """Search a stored design for the values that minimise a metric; store the best as ``name``.

    ``objective`` is a metric such as ``lcts``, ``lcoh``, ``lcoc``, ``annualised_cost`` or ``co2``;
    a leading ``-`` maximises it. ``variables`` is a list of ``{path, parameter, lower, upper}``:
    bounds are ``{value, unit}`` or, for ``size.doublets``, counts. A name is a plant
    ``path.parameter``, ``case.<path>`` or ``<role>.<parameter>`` (every unit of a role).
    An empty list means the case's choices (``size.doublets`` and ``depth``); a list replaces
    them, so restate those to keep searching them. ``evaluations`` counts simulations for each
    doublet count, at least five for each continuous variable. ``constraints`` are limits on
    metrics, ``{metric, minimum, maximum}`` with ``{value, unit}`` limits, either optional.
    Returns the best (its value, parameters and plant), ``feasible``, the ``fixed`` variables the
    plant could not take, the ``trials`` run and the stored ``design``. When no trial is feasible
    the best is the least violating one and its ``reason`` says why.
    """
    plant = load_design(context, design, "optimize")
    case = case_of(context)
    found = await asyncio.to_thread(
        minimize_design, plant, case, objective, variables, constraints, evaluations
    )
    best = found["best"]
    result = {
        "best": best.to_dict(),
        "feasible": found["feasible"],
        "fixed": to_plain(found["fixed"]),
        "trials": len(found["history"]),
    }
    if best["plant"] is not None:
        result["design"] = await save_design(context, name, best["plant"])
    return result


def sample_design(plant, case, metrics, count, seed):
    """Return gemini's sample of the plant over the case's uncertainty."""
    import gemini as gm

    return gm.study.sample(plant, case, metrics, count, seed)


@tool(effect="compute")
async def sample_uncertainty(context, design: str, metrics: list[str], count: int, seed: int):
    """Sample a stored design over the uncertainty the case declares; return a summary per metric.

    The distributions are only those of the case's ``uncertainty`` (set them with ``set_case``);
    a case without any is an error. ``count`` draws are simulated, one run each, from ``seed``.
    Each metric has ``mean``, ``p5``, ``p50`` and ``p95`` in display units and ``failed``, the
    number of draws left out because their run had failed steps.
    """
    plant = load_design(context, design, "sample_uncertainty")
    case = case_of(context)
    sample = await asyncio.to_thread(sample_design, plant, case, metrics, count, seed)
    return to_plain(sample.to_dict())


def sensitivity_of_design(plant, case, metrics):
    """Return gemini's tornado of the plant over the case's uncertainty."""
    import gemini as gm

    return gm.study.sensitivity(plant, case, metrics)


@tool(effect="compute")
async def sensitivity(context, design: str, metrics: list[str]):
    """Rank the case's uncertain values by their effect on the metrics of a stored design.

    Each value the case declares an ``uncertainty`` for is set at its low and high bound; the list
    is sorted by effect, each item ``{parameter, metric, low, high, at_low, at_high, effect}``.
    """
    plant = load_design(context, design, "sensitivity")
    case = case_of(context)
    tornado = await asyncio.to_thread(sensitivity_of_design, plant, case, metrics)
    return to_plain(tornado.to_dict())


def compare_runs(runs, by):
    """Return gemini's comparison of the reports of the runs."""
    import gemini as gm

    reports = [gm.evaluate.report(plant, case, results) for plant, case, results in runs]
    return gm.evaluate.compare(reports, by)


def shown_values(comparison):
    """Return ``[{metric: {value, unit}}]``, one per report, in the display units of the table."""
    frame = comparison.to_frame()
    shown = []
    for position, entry in enumerate(comparison):
        values = {}
        for name in entry["values"]:
            label = next(column for column in frame if column.split(" [")[0] == name)
            unit = label[len(name) + 2 : -1] if label != name else "-"
            number = frame[label].iloc[position]
            values[name] = {"value": None if number != number else float(number), "unit": unit}
        shown.append(values)
    return shown


@tool(effect="compute")
async def compare(context, references: list[str], by: list[str]):
    """Compare stored runs on metrics such as ``lcts`` or ``co2``; return one entry per run.

    Each entry has the run's ``reference``, its metric ``values`` in display units, ``ranks`` (1
    is best, the feasible first), ``pareto`` and ``feasible``, and the ``reasons`` of an
    infeasible run.
    """
    runs = [load_run(context, reference, "compare") for reference in references]
    comparison = await asyncio.to_thread(compare_runs, runs, by)
    entries = to_plain(comparison.to_dict())
    values = shown_values(comparison)
    return [
        {"reference": reference, **entry, "values": shown}
        for reference, entry, shown in zip(references, entries, values)
    ]
