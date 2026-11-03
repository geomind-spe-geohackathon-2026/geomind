"""The tools that size, search, sample and compare stored designs, over the state's case."""

import json
from typing import Literal

from geomind import runtime
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.tools.gemini.case import build_case
from geomind.tools.gemini.explain import range_guidance
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.stored import (
    case_id,
    check_study_free,
    design_stem,
    load_design,
    load_run,
    ran_case,
    save_design,
    save_study,
)

STUDY_TIMEOUT_S = 900
"""How long a study tool waits for gemini; a search past it comes back as a ``timeout`` error."""
CASE_FILE = "case/case.json"


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


def study_of(name, settings, case_parts, plants):
    """Return the ``gm.Study`` named ``name`` over one case and ``{design reference: plant dict}``.

    NOTE: the study names its plants by the references of the stored designs, and its case by
    ``case/case.json``, which stands for the state's case; ``save_study`` keeps the case's id.
    """
    import gemini as gm

    case_data, case_files = case_parts
    data = {"format": 1, "kind": "study", "name": name, "cases": [CASE_FILE]}
    data["plants"] = list(plants)
    data.update({key: value for key, value in settings.items() if value is not None})
    files = {CASE_FILE: json.dumps(case_data).encode()}
    files.update({f"case/{file}": content for file, content in case_files.items()})
    files.update({reference: json.dumps(plant).encode() for reference, plant in plants.items()})
    return gm.Study.from_dict(data, files=files)


def prepared(context, tool_name, name, designs, settings, written):
    """Return ``(ran case, {reference: plant}, gm.Study, case id)`` of a study about to run.

    The name, the settings and the designs are checked, and so is that the study and the designs
    it would store are free, before anything long runs.
    """
    ran = ran_case(context)
    plants = {design: load_design(context, design, tool_name) for design in designs}
    dicts = {design: plant.to_dict(structure=True) for design, plant in plants.items()}
    study = study_of(name, settings, ran, dicts)
    case = case_id(ran)
    check_study_free(context, name, study.to_dict(), case, written, tool_name)
    return ran, plants, study, case


def size_design(plant, case):
    """Return the plant sized for the case, under the backup policy the plant states."""
    import gemini as gm

    return gm.study.size(plant, case)


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"design": reference_schema("design")},
)
async def size_plant(context, design: str, name: str):
    """Size a stored design for the state's case; store the sized plant as design ``name``.

    Sizing reads the plant's ranges (``size.doublets`` min and max, when its class takes doublets)
    and its ``params.backup``; set what is missing with ``set_ranges`` first. The boiler's backup
    policy is the plant's own ``params.backup``: ``peak`` covers the whole heating peak with
    the doublets off, ``none`` covers only what the doublets cannot reach. The policy has no
    default: set it in the plant first, as an assumption when the user gave none. ``name`` names
    the sized design and the study ``study/<name>`` that records the call; a taken name is
    refused. Returns the new design reference, the ``study`` key and
    gemini's notes: what was ``sized`` with its reason, what stayed ``unchanged``, what is
    ``broken`` and the ``simulation`` that judged it.
    """
    settings = {"method": "run", "prepare": ["size"]}
    written = [f"design/{name}"]
    ran, plants, study, case = prepared(context, "size_plant", name, [design], settings, written)
    with range_guidance(plants):
        sized = await runtime.in_gemini_thread(size_design, plants[design], build_case(*ran))
    reference = await save_design(context, name, sized)
    result = {"sizing": to_plain(sized.sizing)}
    found = (study.to_dict(), result)
    key = await save_study(
        context, name, "size_plant", found, ([design], [reference]), reference, case
    )
    return {"design": reference, "study": key, "sizing": result["sizing"]}


def minimize_design(plant, case, objective, evaluations, seed):
    """Return gemini's search of the plant over its ranges and options."""
    import gemini as gm

    return gm.study.minimize(plant, case, objective, evaluations, seed)


def minimized(found):
    """Return gemini's plain form of a search: the best without its plant, as a study keeps it.

    ``best``, ``feasible`` and ``evaluations`` are as before; ``history`` is every trial, from
    gemini's ``Search.to_dict()``.
    """
    best = found["best"].to_dict() | {"plant": None}
    kept = {"best": best, "feasible": found["feasible"], "evaluations": found["evaluations"]}
    return {**kept, "history": found.to_dict()["history"]}


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"design": reference_schema("design")},
)
async def optimize(context, design: str, objective: str, evaluations: int, seed: int, name: str):
    """Search a stored design for the values that minimise a metric; store the best as ``name``.

    ``objective`` is a metric such as ``lcts``, ``lcoh``, ``lcoc``, ``annualised_cost`` or ``co2``;
    a leading ``-`` maximises it. The variables are the ranges and options of the design (set them
    with ``set_ranges``); a design with none is gemini's error. The constraints are the case's
    requirements, which the user owns. ``evaluations`` and ``seed`` have no default. ``name``
    names the stored best design and the study ``study/<name>`` that records the call; a taken
    name is refused. Returns the ``best`` (its value, parameters and plant, in display units),
    ``feasible``, the ``trials`` run, the stored ``design`` and the ``study`` key. When no trial
    is feasible the best is the least violating one and its ``reason`` says why. A search that
    takes longer than 15 minutes comes back as a ``timeout`` error: ask for fewer evaluations.
    """
    settings = {"method": "minimize", "objective": objective, "evaluations": evaluations}
    settings["seed"] = seed
    written = [f"design/{name}"]
    ran, plants, study, case = prepared(context, "optimize", name, [design], settings, written)
    with range_guidance(plants):
        found = await runtime.in_gemini_thread(
            minimize_design, plants[design], build_case(*ran), objective, evaluations, seed
        )
    best = found["best"]
    result = {
        "best": best.to_dict(),
        "feasible": found["feasible"],
        "trials": len(found["history"]),
    }
    wrote = []
    if best["plant"] is not None:
        wrote = [await save_design(context, name, best["plant"])]
    recommended = wrote[0] if wrote and found["feasible"] else None
    recorded = (study.to_dict(), minimized(found))
    key = await save_study(
        context, name, "optimize", recorded, ([design], wrote), recommended, case
    )
    return result | {"study": key} | ({"design": wrote[0]} if wrote else {})


def sample_design(plant, case, metrics, samples, seed):
    """Return gemini's sample of the plant over the case's uncertainty."""
    import gemini as gm

    return gm.study.sample(plant, case, metrics, samples, seed)


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"design": reference_schema("design")},
)
async def sample_uncertainty(
    context, design: str, metrics: list[str], samples: int, seed: int, name: str
):
    """Sample a design over the case's uncertainty (from the user or the case, never made up).

    Returns a summary per metric.

    The distributions are only those of the case's ``uncertainty`` (set them with ``set_case``);
    a case without any is an error. ``samples`` draws are simulated, one run each, from ``seed``.
    ``name`` names the study ``study/<name>`` that records the call; a taken name is refused.
    Returns the ``study`` key and, in ``summary``, each metric's ``mean``, ``p5``, ``p50`` and
    ``p95`` in display units and ``failed``, the number of draws left out because their run had
    failed steps.
    """
    settings = {"method": "sample", "metrics": metrics, "samples": samples, "seed": seed}
    ran, plants, study, case = prepared(context, "sample_uncertainty", name, [design], settings, [])
    sample = await runtime.in_gemini_thread(
        sample_design, plants[design], build_case(*ran), metrics, samples, seed
    )
    result = to_plain(sample.to_dict())
    found = (study.to_dict(), result)
    key = await save_study(context, name, "sample_uncertainty", found, ([design], []), None, case)
    return {"study": key, **result}


def sensitivity_of_design(plant, case, metrics):
    """Return gemini's tornado of the plant over the case's uncertainty."""
    import gemini as gm

    return gm.study.sensitivity(plant, case, metrics)


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"design": reference_schema("design")},
)
async def sensitivity(context, design: str, metrics: list[str], name: str):
    """Rank the case's uncertain values (from the user or the case, never made up) by effect.

    The metrics are those of a stored design.

    Each value the case declares an ``uncertainty`` for is set at its low and high bound. ``name``
    names the study ``study/<name>`` that records the call; a taken name is refused. Returns the
    ``study`` key and ``rows``, sorted by effect, each ``{parameter, metric, low, high, at_low,
    at_high, effect}``.
    """
    settings = {"method": "sensitivity", "metrics": metrics}
    ran, plants, study, case = prepared(context, "sensitivity", name, [design], settings, [])
    tornado = await runtime.in_gemini_thread(
        sensitivity_of_design, plants[design], build_case(*ran), metrics
    )
    result = to_plain(tornado.to_dict())
    found = (study.to_dict(), result)
    key = await save_study(context, name, "sensitivity", found, ([design], []), None, case)
    return {"study": key, **result}


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


async def store_runs(context, name, result):
    """Store the plant each run ended with as ``design/<name>_<plant>``; return the runs shown."""
    comparison = result.to_dict()["comparison"]
    runs = []
    for run in result.runs:
        reference = await save_design(context, f"{name}_{run.plant_name}", run.plant)
        entries = ranked_entries(comparison, run.case_name)
        runs.append(run_entry(run, entries.get(len(runs)), reference))
    return runs


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"designs": reference_schema("design", many=True)},
)
async def run_study(
    context,
    designs: list[str],
    method: Literal["run", "minimize", "sample", "sensitivity"],
    name: str,
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
    ``sensitivity``; ``prepare=["size"]`` sizes each design first, from its ranges and its own
    ``params.backup``.
    The settings a method needs are gemini's: ``minimize`` needs ``objective``, ``evaluations``
    and ``seed``; ``sample`` needs ``metrics``, ``samples`` and ``seed``; ``sensitivity`` needs
    ``metrics``. A missing or unread setting is gemini's error; none has a default. ``name``
    names the study ``study/<name>`` that records the call, and each design it ends with is
    stored as ``design/<name>_<plant name>``; a taken name is refused. Returns the ``study`` key
    and ``runs``, one per design in order: ``plant_name``, ``feasible``, ``verdict``, ``metrics``
    in display units, ``ranks`` and ``pareto`` (rank 1 is best, over the objective then the
    metrics), ``note``, what the method ``found`` and the stored ``design`` the run ended with
    (the sized or the best plant). ``best`` names the feasible design ranked first by the
    objective, if any.
    """
    settings = {"method": method, "objective": objective, "metrics": metrics, "seed": seed}
    settings |= {"evaluations": evaluations, "samples": samples, "prepare": prepare}
    written = [f"design/{name}_{design_stem(design)}" for design in designs]
    _, plants, study, case = prepared(context, "run_study", name, designs, settings, written)
    with range_guidance(plants):
        result = await runtime.in_gemini_thread(study_runs, study)
    runs = await store_runs(context, name, result)
    best = {case_name: run and run.plant_name for case_name, run in result.best.items()}
    stored = {item["plant_name"]: item["design"] for item in runs}
    first = next((plant for plant in best.values() if plant is not None), None)
    found = (study.to_dict(), result.to_dict())
    kept = (designs, [item["design"] for item in runs])
    key = await save_study(context, name, "run_study", found, kept, stored.get(first), case)
    return {"study": key, "runs": runs, "best": best}


def compare_runs(runs, by):
    """Return ``(comparison, reports)`` of the runs: gemini's ranking and each run's report."""
    import gemini as gm

    reports = [gm.evaluate.report(plant, case, results) for plant, case, results in runs]
    return gm.evaluate.compare(reports, by), reports


@tool(effect="compute", late_schemas={"references": reference_schema("result", many=True)})
async def compare(context, references: list[str], by: list[str]):
    """Compare stored runs on metrics such as ``lcts`` or ``co2``; return one entry per run.

    Each entry has the run's ``reference``, its metric ``values`` in display units, ``ranks`` (1
    is best, the feasible first), ``pareto`` and ``feasible``, and the ``reasons`` of an
    infeasible run.
    """
    runs = [load_run(context, reference, "compare") for reference in references]
    comparison, reports = await runtime.in_gemini_thread(compare_runs, runs, by)
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


EVOLVE_SETTINGS = {
    "evaluations": "evolve_evaluations",
    "population": "evolve_population",
    "seed": "evolve_seed",
    "polish": "evolve_polish",
}
"""The settings of ``evolve_structure`` by gemini's argument, each required, with no default."""


def evolve_settings():
    """Return gemini's ``evolve`` settings from the runtime; an unset one is refused by name."""
    found = {argument: runtime.get(setting) for argument, setting in EVOLVE_SETTINGS.items()}
    missing = [EVOLVE_SETTINGS[argument] for argument, value in found.items() if value is None]
    if missing:
        names = ", ".join(f"GEOMIND_{name.upper()}" for name in missing)
        raise ToolError(f"evolve_structure: {names} not set; expected each", code="not_allowed")
    return found


def evolve_design(plant, case, objectives, settings):
    """Return gemini's genetic search over the plant's structures and values."""
    import gemini as gm

    return gm.study.evolve(
        plant,
        case,
        objectives,
        settings["evaluations"],
        settings["seed"],
        population=settings["population"],
        polish=settings["polish"],
    )


def front_entry(design, reference):
    """Return one design of the front as the model reads it: no plant and no parameters."""
    shown = design.to_dict()
    kept = {key: shown.get(key) for key in ("structure", "metrics", "feasible", "reason")}
    return {"design": reference, **kept}


def evolved(found):
    """Return gemini's plain form of an evolution, as a study keeps it: no plants."""
    data = found.to_dict()
    front = [without_plant(item) for item in data["front"]]
    return {**data, "front": front, "best": without_plant(data["best"])}


def without_plant(item):
    """Return a design of an evolution without its plant, which its stored design keeps."""
    return {**item, "plant": None}


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"design": reference_schema("design")},
)
async def evolve_structure(context, design: str, objectives: list[str], name: str):
    """Search a superstructure's structures and values by gemini's genetic algorithm.

    ``design`` holds optional modules (``optional``) and choice groups (``choices``) with their
    ranges; ``objectives`` are the metrics the case or the brief names to minimise (a leading
    ``-`` maximises), never ones you choose. The evaluations, population, seed and polish are
    settings, not yours. Each design of the front (none beats it on every objective) is stored
    as ``design/<name>_<n>``; the answer lists each with its ``structure``, ``metrics``,
    ``feasible`` and ``reason``, then ``best`` (on the first objective), the ``evaluations``
    run, the ``invalid`` structures refused and the ``study`` key. Take the chosen design on as
    any other: size, simulate, check.
    """
    settings = evolve_settings()
    study_settings = {"method": "evolve", "objectives": objectives, **settings}
    ran, plants, study, case = prepared(
        context, "evolve_structure", name, [design], study_settings, []
    )
    found = await runtime.in_gemini_thread(
        evolve_design, plants[design], build_case(*ran), objectives, settings
    )
    front, wrote = [], []
    for number, item in enumerate(found["front"], 1):
        reference = await save_design(context, f"{name}_{number}", item["plant"])
        wrote.append(reference)
        front.append(front_entry(item, reference))
    best = next(
        (entry["design"] for item, entry in zip(found["front"], front) if item is found["best"]),
        None,
    )
    recommended = best if found["best"]["feasible"] else None
    recorded = (study.to_dict(), evolved(found))
    key = await save_study(
        context, name, "evolve_structure", recorded, ([design], wrote), recommended, case
    )
    return {
        "front": front,
        "best": best,
        "evaluations": found["evaluations"],
        "invalid": found["invalid"],
        "study": key,
    }
