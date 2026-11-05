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
    full_run,
    simulated_run,
    load_design,
    load_run,
    ran_case,
    save_design,
    save_study,
)

STUDY_TIMEOUT_S = 900
"""How long a study tool waits for gemini; a search past it comes back as a ``timeout`` error."""
CASE_FILE = "case/case.json"


FIGURES = 5
"""Significant digits of a figure a study tool returns: ``49.281``, not 16 digits."""


def figures(found):
    """Return ``found`` with every float to ``FIGURES`` significant digits (QA-099).

    The study tools returned the trials, ranks and sensitivity rows with 15 to 17 digits, which
    the answers quoted; the stored study keeps gemini's full numbers, only what the model reads
    is rounded. An integer, a bool, a NaN or an infinity is left as it is.
    """
    if isinstance(found, dict):
        return {key: figures(item) for key, item in found.items()}
    if isinstance(found, (list, tuple)):
        return [figures(item) for item in found]
    if isinstance(found, float) and found == found and abs(found) != float("inf"):
        return float(f"{found:.{FIGURES}g}")
    return found


EVALUATIONS_NOTE = (
    "evaluations is gemini's budget per doublet count; found.evaluations counts every trial of "
    "every count searched"
)
"""Why a search's trials can exceed the ``evaluations`` asked (QA-179: 80 trials for 30)."""


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
    from geomind.tools.gemini.runs import single_choices

    plants = {design: load_design(context, design, tool_name) for design in designs}
    for plant in plants.values():
        single_choices(plant)
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

    Skill `simulating-a-plant`.
    """
    from geomind.tools.gemini.plants import plant_issues

    settings = {"method": "run", "prepare": ["size"]}
    written = [f"design/{name}"]
    ran, plants, study, case = prepared(context, "size_plant", name, [design], settings, written)
    with range_guidance(plants):
        sized = await runtime.in_gemini_thread(size_design, plants[design], build_case(*ran))
    reference = await save_design(context, name, sized)
    result = {"sizing": to_plain(sized.sizing)}
    found = (study.to_dict(), result)
    runs = [await simulated_run(context, reference, ran, {"study": name})]
    key = await save_study(
        context, name, "size_plant", found, ([design], [reference]), reference, case, runs=runs
    )
    issues = await runtime.in_gemini_thread(plant_issues, context, sized)
    shown = {"design": reference, "study": key, "sizing": result["sizing"], **issues}
    return {**shown, "missing": len(issues["issues"])}


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

    Skill `simulating-a-plant`.
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
        "evaluations_note": EVALUATIONS_NOTE,
    }
    wrote = []
    if best["plant"] is not None:
        wrote = [await save_design(context, name, best["plant"])]
    recommended = wrote[0] if wrote and found["feasible"] else None
    recorded = (study.to_dict(), minimized(found))
    runs = [await simulated_run(context, wrote[0], ran, {"study": name})] if wrote else []
    key = await save_study(
        context, name, "optimize", recorded, ([design], wrote), recommended, case, runs=runs
    )
    return figures(result | {"study": key} | ({"design": wrote[0]} if wrote else {}))


def sample_design(plant, case, metrics, samples, seed, percentiles=None):
    """Return gemini's sample of the plant over the case's uncertainty.

    ``percentiles`` (gemini 0.6.27) adds ``p<n>`` to the summary; left out when not asked for.
    """
    import gemini as gm

    extra = {} if not percentiles else {"percentiles": list(percentiles)}
    return gm.study.sample(plant, case, metrics, samples, seed, **extra)


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"design": reference_schema("design")},
)
async def sample_uncertainty(
    context,
    design: str,
    metrics: list[str],
    samples: int,
    seed: int,
    name: str,
    values: list[str] | None = None,
    percentiles: list[float] | None = None,
):
    """Sample a design over the case's uncertainty (from the user or the case, never made up).

    Skill `economics`.
    """
    settings = {"method": "sample", "metrics": metrics, "samples": samples, "seed": seed}
    if percentiles:
        settings["percentiles"] = list(percentiles)
    ran, plants, study, case = prepared(context, "sample_uncertainty", name, [design], settings, [])
    data, files = (
        (ran[0], ran[1])
        if not values
        else only_uncertainty(ran[0], ran[1], values, "sample_uncertainty")
    )
    sample = await runtime.in_gemini_thread(
        sample_design,
        plants[design],
        build_case(data, files),
        metrics,
        samples,
        seed,
        percentiles,
    )
    result = to_plain(sample.to_dict())
    result["varied"] = varied(result)
    found = (study.to_dict(), result)
    key = await save_study(context, name, "sample_uncertainty", found, ([design], []), None, case)
    return figures({"study": key, **result})


def varied(result):
    """Return the case paths gemini drew, from the first draw's parameters."""
    first = next(iter(result.get("samples") or ()), {})
    return sorted((first.get("parameters") or {}).keys())


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
async def sensitivity(
    context, design: str, metrics: list[str], name: str, values: list[str] | None = None
):
    """Rank the case's uncertain values (from the user or the case, never made up) by effect.

    Skill `economics`.
    """
    settings = {"method": "sensitivity", "metrics": metrics}
    ran, plants, study, case = prepared(context, "sensitivity", name, [design], settings, [])
    data, files = (ran[0], ran[1]) if not values else only_uncertainty(ran[0], ran[1], values)
    tornado = await runtime.in_gemini_thread(
        sensitivity_of_design, plants[design], build_case(data, files), metrics
    )
    result = to_plain(tornado.to_dict())
    found = (study.to_dict(), result)
    key = await save_study(context, name, "sensitivity", found, ([design], []), None, case)
    return figures({"study": key, **result, **left_out(ran[0], ran[1], values)})


def left_out(data, files, values):
    """Return ``{left_out, scope}`` when ``values`` names only some declared uncertainties.

    A tornado over a subset ranks that subset only (QA-263): the values it left out may move the
    metric more, so no value of it is the dominant driver of the case.
    """
    if not values:
        return {}
    names = {str(item).removeprefix("case.") for item in values}
    rest = [item for item in case_uncertainty(data, files) if item not in names]
    if not rest:
        return {}
    scope = (
        "this ranks only the named values; the case declares more uncertain values, listed in "
        "left_out, that were not varied: never call one of the named values the case's dominant "
        "driver; run sensitivity without values for the whole ranking"
    )
    return {"left_out": rest, "scope": scope}


def case_uncertainty(data, files):
    """Return the dotted paths of every value the case declares an ``uncertainty`` for."""
    economics = data.get("economics") if isinstance(data, dict) else None
    sheet = None
    if isinstance(economics, str) and economics in (files or {}):
        sheet = json.loads((files or {})[economics])
    elif isinstance(economics, dict):
        sheet = economics
    rest = {k: v for k, v in (data or {}).items() if k != "economics"}
    return declared_uncertainty(rest) + declared_uncertainty(sheet or {}, "economics.")


def declared_uncertainty(data, prefix=""):
    """Return the dotted paths of the case dict ``data`` whose value declares an ``uncertainty``."""
    found = []
    for key, node in data.items() if isinstance(data, dict) else ():
        path = f"{prefix}{key}"
        if isinstance(node, dict):
            if "uncertainty" in node:
                found.append(path)
            found += declared_uncertainty(node, f"{path}.")
    return found


def kept_uncertainty(node, names, prefix):
    """Drop, in place, the ``uncertainty`` of every value of ``node`` whose path is not named."""
    for key, child in node.items() if isinstance(node, dict) else ():
        path = f"{prefix}{key}"
        if isinstance(child, dict):
            if "uncertainty" in child and path not in names:
                child.pop("uncertainty")
            kept_uncertainty(child, names, f"{path}.")


def only_uncertainty(data, files, values, tool_name="sensitivity"):
    """Return ``(case dict, files)`` with the ``uncertainty`` of the named ``values`` only.

    A sensitivity of the drivers a user names moves only those, not every value the case
    declares (QA-131). The economics may be a file of the case (``"economics": "<name>"``); its
    values are ``economics.<path>``. A name the case declares no uncertainty for is an error
    listing the declared ones: the ranges are set in the case first, with ``set_case``.
    """
    import copy

    names = [str(item).removeprefix("case.") for item in values]
    kept, files = copy.deepcopy(data), dict(files or {})
    economics = kept.get("economics")
    sheet = None
    if isinstance(economics, str) and economics in files:
        sheet = json.loads(files[economics])
    elif isinstance(economics, dict):
        sheet = kept.pop("economics")
    declared = declared_uncertainty({k: v for k, v in kept.items() if k != "economics"})
    declared += declared_uncertainty(sheet or {}, "economics.")
    unknown = [item for item in names if item not in declared]
    if unknown:
        raise ToolError(
            f"{tool_name}: values = {unknown}: the case declares no uncertainty for them; "
            f"declared: {declared or 'none'}. Set each range in the case first: "
            "set_case(economics={key: {value, unit, uncertainty: {kind: 'uniform', min, max}}}) "
            "for an economics value, "
            "with the range the user gave",
            path="values",
        )
    kept_uncertainty(kept, names, "")
    if sheet is not None:
        kept_uncertainty(sheet, names, "economics.")
        if isinstance(economics, str):
            files[economics] = json.dumps(sheet).encode()
        else:
            kept["economics"] = sheet
    return kept, files


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
    if isinstance(found, dict) and "evaluations" in found:
        result["evaluations_note"] = EVALUATIONS_NOTE
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

    Skill `comparing-designs`.
    """
    settings = {"method": method, "objective": objective, "metrics": metrics, "seed": seed}
    settings |= {"evaluations": evaluations, "samples": samples, "prepare": prepare}
    written = [f"design/{name}_{design_stem(design)}" for design in designs]
    ran, plants, study, case = prepared(context, "run_study", name, designs, settings, written)
    with range_guidance(plants):
        result = await runtime.in_gemini_thread(study_runs, study)
    runs = await store_runs(context, name, result)
    best = {case_name: run and run.plant_name for case_name, run in result.best.items()}
    stored = {item["plant_name"]: item["design"] for item in runs}
    first = next((plant for plant in best.values() if plant is not None), None)
    found = (study.to_dict(), result.to_dict())
    kept = (designs, [item["design"] for item in runs])
    full = [
        await full_run(context, run, item["design"], ran, {"study": name, "run": index})
        for index, (run, item) in enumerate(zip(result.runs, runs, strict=True))
    ]
    key = await save_study(
        context, name, "run_study", found, kept, stored.get(first), case, runs=full
    )
    return figures({"study": key, "runs": runs, "best": best})


def compare_runs(runs, by):
    """Return ``(comparison, reports)`` of the runs: gemini's ranking and each run's report."""
    import gemini as gm

    reports = [gm.evaluate.report(plant, case, results) for plant, case, results in runs]
    return gm.evaluate.compare(reports, by), reports


@tool(effect="compute", late_schemas={"references": reference_schema("result", many=True)})
async def compare(context, references: list[str], by: list[str]):
    """Compare stored runs on metrics such as ``lcts`` or ``co2``; return one entry per run.

    Skill `comparing-designs`.
    """
    runs = [load_run(context, reference, "compare") for reference in references]
    comparison, reports = await runtime.in_gemini_thread(compare_runs, runs, by)
    entries = to_plain(comparison.to_dict())
    shown = [report.to_dict() for report in reports]
    return figures(
        [
            {
                "reference": reference,
                **entry,
                "values": {name: display[name] for name in entry["values"]},
            }
            for reference, entry, display in zip(references, entries, shown)
        ]
    )


EVOLVE_SETTINGS = {
    "evaluations": "evolve_evaluations",
    "population": "evolve_population",
    "seed": "evolve_seed",
    "polish": "evolve_polish",
}
"""The settings of ``evolve_structure`` by gemini's argument, each required, with no default."""
STOP_SETTINGS = {
    "generations": "evolve_stop_generations",
    "seconds": "evolve_stop_seconds",
}
"""The settings of gemini's ``evolve(stop=...)`` by its key, each required: a number or ``off``."""
STOPPED = {
    "budget": "it ran the {evaluations} simulations of GEOMIND_EVOLVE_EVALUATIONS",
    "stalled": "no new candidate was left to simulate for several generations in a row",
    "converged": (
        "the feasible front did not change for {generations} generations in a row "
        "(GEOMIND_EVOLVE_STOP_GENERATIONS)"
    ),
    "seconds": "it reached the time limit of {seconds} s (GEOMIND_EVOLVE_STOP_SECONDS)",
}
"""Why gemini's search stopped, by its ``budget.stopped``, in words the model can quote."""


def setting_name(setting):
    """Return the environment variable of a runtime setting."""
    return f"GEOMIND_{setting.upper()}"


def evolve_settings():
    """Return gemini's ``evolve`` settings from the runtime; an unset one is refused by name.

    ``stop`` is gemini's ``{"generations", "seconds"}`` without the keys set ``off``, ``None``
    when both are: the search then spends its budget.
    """
    names = {**EVOLVE_SETTINGS, **STOP_SETTINGS}
    found = {argument: runtime.get(setting) for argument, setting in names.items()}
    missing = [names[argument] for argument, value in found.items() if value is None]
    if missing:
        listed = ", ".join(setting_name(name) for name in missing)
        raise ToolError(
            f"evolve_structure: {listed} not set; expected each (a stop setting takes off)",
            code="not_allowed",
        )
    stop = {key: found.pop(key) for key in STOP_SETTINGS}
    stop = {key: value for key, value in stop.items() if value != runtime.OFF}
    return {**found, "stop": stop or None}


def stop_reason(stopped, settings):
    """Return why the search stopped, from gemini's ``budget.stopped`` and the settings."""
    text = STOPPED.get(stopped)
    if text is None:
        return f"gemini says {stopped}"
    return text.format(evaluations=settings["evaluations"], **(settings["stop"] or {}))


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
        stop=settings["stop"],
    )


def front_table(frame):
    """Return gemini's ``to_frame()`` of a front compactly: ``{columns, rows}``, NaN as null."""
    import math

    rows = [
        [None if isinstance(value, float) and math.isnan(value) else value for value in row]
        for row in frame.itertuples(index=False, name=None)
    ]
    return {"columns": [str(column) for column in frame.columns], "rows": to_plain(rows)}


def front_entry(design, reference):
    """Return one design of the front as the model reads it: no plant and no parameters."""
    shown = design.to_dict()
    kept = {key: shown.get(key) for key in ("structure", "metrics", "feasible", "reason")}
    return {"design": reference, **kept}


def evolved(found):
    """Return gemini's plain form of an evolution, as a study keeps it: no plants.

    It carries gemini's own words and table of the search, ``explanation`` (``explain()``) and
    ``table`` (``to_frame()``, the front in display units), for the lead and the explainer to
    quote.
    """
    data = found.to_dict()
    front = [without_plant(item) for item in data["front"]]
    kept = {**data, "front": front, "best": without_plant(data["best"])}
    return kept | {"explanation": found.explain(), "table": front_table(found.to_frame())}


def without_plant(item):
    """Return a design of an evolution without its plant, which its stored design keeps."""
    return {**item, "plant": None}


async def stored_front(context, name, found):
    """Store each design of an evolve's front as ``<name>_<n>``; return ``(front, best)``."""
    front = []
    for number, item in enumerate(found["front"], 1):
        reference = await save_design(context, f"{name}_{number}", item["plant"])
        front.append(front_entry(item, reference))
    best = next(
        (entry["design"] for item, entry in zip(found["front"], front) if item is found["best"]),
        None,
    )
    return front, best


@tool(
    effect="compute",
    timeout=STUDY_TIMEOUT_S,
    runs_alone=True,
    late_schemas={"design": reference_schema("design")},
)
async def evolve_structure(context, design: str, objectives: list[str], name: str):
    """Search a superstructure's structures and values by gemini's genetic algorithm.

    Skill `comparing-designs`.
    """
    settings = evolve_settings()
    study_settings = {"method": "evolve", "objectives": objectives, **settings}
    ran, plants, study, case = prepared(
        context, "evolve_structure", name, [design], study_settings, []
    )
    found = await runtime.in_gemini_thread(
        evolve_design, plants[design], build_case(*ran), objectives, settings
    )
    front, best = await stored_front(context, name, found)
    recommended = best if found["best"]["feasible"] else None
    kept = await runtime.in_gemini_thread(evolved, found)
    recorded = (study.to_dict(), kept)
    runs = [await simulated_run(context, best, ran, {"study": name})] if best else []
    wrote = ([design], [entry["design"] for entry in front])
    key = await save_study(
        context, name, "evolve_structure", recorded, wrote, recommended, case, runs=runs
    )
    return figures(
        {
            "front": front,
            "best": best,
            "evaluations": found["evaluations"],
            "invalid": found["invalid"],
            "rejected": [
                {"structure": item["structure"], "reasons": item["reasons"]}
                for item in kept["rejected"]
            ],
            "stopped": kept["budget"]["stopped"],
            "why": stop_reason(kept["budget"]["stopped"], settings),
            "study": key,
        }
    )
