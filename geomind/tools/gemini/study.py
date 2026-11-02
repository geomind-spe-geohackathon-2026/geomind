"""The tools that size, search, sample and compare stored designs, over the state's case."""

import asyncio
import json
from typing import Literal

from geomind.tools.base import tool
from geomind.tools.gemini.case import case_of
from geomind.tools.gemini.stored import load_design, load_run, ran_case, save_design

STUDY_TIMEOUT_S = 900
"""How long a study tool waits for gemini; a search past it comes back as a ``timeout`` error."""
CASE_FILE = "case/case.json"
PLANTS_FOLDER = "plants/"


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


def size_design(plant, case):
    """Return the plant sized for the case, under the backup policy the plant states."""
    import gemini as gm

    return gm.study.size(plant, case)


@tool(effect="compute", timeout=STUDY_TIMEOUT_S)
async def size_plant(context, design: str, name: str):
    """Size a stored design for the state's case and store the sized plant as design ``name``.

    The backup policy for the boiler is the plant's own ``params.backup``: ``peak`` covers the
    whole heating peak with the doublets off, ``none`` covers only what the doublets cannot
    reach. The policy has no default: set it in the plant first, as an assumption when the user
    gave none. Returns the new design reference and gemini's notes: what was ``sized`` with its
    reason, what stayed ``unchanged``, what is ``broken`` and the ``simulation`` that judged it.
    """
    plant = load_design(context, design, "size_plant")
    case = case_of(context)
    sized = await asyncio.to_thread(size_design, plant, case)
    reference = await save_design(context, name, sized)
    return {"design": reference, "sizing": to_plain(sized.sizing)}


def minimize_design(plant, case, objective, evaluations, seed):
    """Return gemini's search of the plant over its ranges and options."""
    import gemini as gm

    return gm.study.minimize(plant, case, objective, evaluations, seed)


@tool(effect="compute", timeout=STUDY_TIMEOUT_S)
async def optimize(context, design: str, objective: str, evaluations: int, seed: int, name: str):
    """Search a stored design for the values that minimise a metric; store the best as ``name``.

    ``objective`` is a metric such as ``lcts``, ``lcoh``, ``lcoc``, ``annualised_cost`` or ``co2``;
    a leading ``-`` maximises it. The variables are the ranges and options of the design (set them
    with ``set_ranges``); a design with none is gemini's error. The constraints are the case's
    requirements, which the user owns. ``evaluations`` and ``seed`` have no default. Returns the
    ``best`` (its value, parameters and plant, in display units), ``feasible``, the ``trials``
    run and the stored ``design``. When no trial is feasible the best is the least violating one
    and its ``reason`` says why. A search that takes longer than 15 minutes comes back as a
    ``timeout`` error: ask for fewer evaluations.
    """
    plant = load_design(context, design, "optimize")
    case = case_of(context)
    found = await asyncio.to_thread(minimize_design, plant, case, objective, evaluations, seed)
    best = found["best"]
    result = {
        "best": best.to_dict(),
        "feasible": found["feasible"],
        "trials": len(found["history"]),
    }
    if best["plant"] is not None:
        result["design"] = await save_design(context, name, best["plant"])
    return result


def sample_design(plant, case, metrics, samples, seed):
    """Return gemini's sample of the plant over the case's uncertainty."""
    import gemini as gm

    return gm.study.sample(plant, case, metrics, samples, seed)


@tool(effect="compute", timeout=STUDY_TIMEOUT_S)
async def sample_uncertainty(context, design: str, metrics: list[str], samples: int, seed: int):
    """Sample a stored design over the uncertainty the case declares; return a summary per metric.

    The distributions are only those of the case's ``uncertainty`` (set them with ``set_case``);
    a case without any is an error. ``samples`` draws are simulated, one run each, from ``seed``.
    Each metric has ``mean``, ``p5``, ``p50`` and ``p95`` in display units and ``failed``, the
    number of draws left out because their run had failed steps.
    """
    plant = load_design(context, design, "sample_uncertainty")
    case = case_of(context)
    sample = await asyncio.to_thread(sample_design, plant, case, metrics, samples, seed)
    return to_plain(sample.to_dict())


def sensitivity_of_design(plant, case, metrics):
    """Return gemini's tornado of the plant over the case's uncertainty."""
    import gemini as gm

    return gm.study.sensitivity(plant, case, metrics)


@tool(effect="compute", timeout=STUDY_TIMEOUT_S)
async def sensitivity(context, design: str, metrics: list[str]):
    """Rank the case's uncertain values by their effect on the metrics of a stored design.

    Each value the case declares an ``uncertainty`` for is set at its low and high bound; the list
    is sorted by effect, each item ``{parameter, metric, low, high, at_low, at_high, effect}``.
    """
    plant = load_design(context, design, "sensitivity")
    case = case_of(context)
    tornado = await asyncio.to_thread(sensitivity_of_design, plant, case, metrics)
    return to_plain(tornado.to_dict())


def design_stem(design):
    """Return the name of a stored design reference, ``design/<name>`` without its prefix."""
    return design.rsplit("/", 1)[-1]


def study_of(settings, case_parts, plants):
    """Return the ``gm.Study`` over one case and the plants ``{name: plant dict}``."""
    import gemini as gm

    case_data, case_files = case_parts
    data = {"format": 1, "kind": "study", "name": "study", "cases": [CASE_FILE]}
    data["plants"] = [f"{PLANTS_FOLDER}{name}.json" for name in plants]
    data.update({key: value for key, value in settings.items() if value is not None})
    files = {CASE_FILE: json.dumps(case_data).encode()}
    files.update({f"case/{name}": content for name, content in case_files.items()})
    for name, plant in plants.items():
        files[f"{PLANTS_FOLDER}{name}.json"] = json.dumps(plant).encode()
    return gm.Study.from_dict(data, files=files)


def study_runs(study):
    """Return gemini's result of running the study."""
    return study.run()


def ranked_entries(comparison, case_name):
    """Return ``{run index: entry}`` of a case from the plain form of the comparison."""
    return {entry["index"]: entry for entry in comparison.get(case_name, [])}


def run_entry(run, entry, reference):
    """Return one run as plain JSON in display units, with its rank when the study ranked."""
    report = run.report.to_dict()
    found = run.to_dict()["found"]
    if isinstance(found, dict):
        found = {key: value for key, value in found.items() if key != "history"}
    result = {
        "plant_name": run.plant_name,
        "design": reference,
        "feasible": run.verdict["feasible"],
        "verdict": run.verdict.to_dict(),
        "metrics": {name: report[name] for name in run.metrics},
        "note": run.note,
        "found": found,
    }
    if entry is not None:
        result |= {"ranks": entry["ranks"], "pareto": entry["pareto"]}
    return result


@tool(effect="compute", timeout=STUDY_TIMEOUT_S)
async def run_study(
    context,
    designs: list[str],
    method: Literal["run", "minimize", "sample", "sensitivity"],
    objective: str | None = None,
    metrics: list[str] | None = None,
    evaluations: int | None = None,
    seed: int | None = None,
    samples: int | None = None,
    prepare: list[Literal["size"]] | None = None,
):
    """Run one study over several stored designs on the state's case and rank them.

    This is how alternatives are compared: one study over several topologies. ``method`` is
    ``run`` (simulate as it is), ``minimize`` (search each design's ranges), ``sample`` or
    ``sensitivity``; ``prepare=["size"]`` sizes each design first, under its own ``params.backup``.
    The settings a method needs are gemini's: ``minimize`` needs ``objective``, ``evaluations``
    and ``seed``; ``sample`` needs ``metrics``, ``samples`` and ``seed``; ``sensitivity`` needs
    ``metrics``. A missing or unread setting is gemini's error; none has a default. Returns
    ``runs``, one per design in order: ``plant_name``, ``feasible``, ``verdict``, ``metrics`` in
    display units, ``ranks`` and ``pareto`` (rank 1 is best, over the objective then the metrics),
    ``note``, what the method ``found`` and the stored ``design`` the run ended with (the sized or
    the best plant). ``best`` names the feasible design ranked first by the objective, if any.
    """
    ran = ran_case(context)
    plants = {design_stem(design): load_design(context, design, "run_study") for design in designs}
    settings = {"method": method, "objective": objective, "metrics": metrics, "seed": seed}
    settings |= {"evaluations": evaluations, "samples": samples, "prepare": prepare}
    study = study_of(
        settings, ran, {name: plant.to_dict(structure=True) for name, plant in plants.items()}
    )
    result = await asyncio.to_thread(study_runs, study)
    comparison = result.to_dict()["comparison"]
    runs = []
    for run in result.runs:
        reference = await save_design(context, f"{run.plant_name}_best", run.plant)
        entries = ranked_entries(comparison, run.case_name)
        runs.append(run_entry(run, entries.get(len(runs)), reference))
    best = {name: None if run is None else run.plant_name for name, run in result.best.items()}
    return {"runs": runs, "best": best}


def compare_runs(runs, by):
    """Return ``(comparison, reports)`` of the runs: gemini's ranking and each run's report."""
    import gemini as gm

    reports = [gm.evaluate.report(plant, case, results) for plant, case, results in runs]
    return gm.evaluate.compare(reports, by), reports


@tool(effect="compute")
async def compare(context, references: list[str], by: list[str]):
    """Compare stored runs on metrics such as ``lcts`` or ``co2``; return one entry per run.

    Each entry has the run's ``reference``, its metric ``values`` in display units, ``ranks`` (1
    is best, the feasible first), ``pareto`` and ``feasible``, and the ``reasons`` of an
    infeasible run.
    """
    runs = [load_run(context, reference, "compare") for reference in references]
    comparison, reports = await asyncio.to_thread(compare_runs, runs, by)
    entries = to_plain(comparison.to_dict())
    shown = [report.to_dict() for report in reports]
    return [
        {
            "reference": reference,
            **entry,
            "values": {name: display[name] for name in entry["values"]},
        }
        for reference, entry, display in zip(references, entries, shown)
    ]
