"""The study tools over gemini's example cases: size, search, sample, run and compare."""

import asyncio
import functools
import json

import pytest

from geomind.tools.gemini import study
from geomind.tools.gemini.stored import ran_case, save_design, save_run
from tests.fixtures.cases import case_context, example_names, example_plant

SHALLOW = "shallow_district"
HEAT_PUMP = "HeatingHeatPumpCoolingPlant"


async def started(name, plant=None, reference="start"):
    """Return ``(context, design reference)``: the example's case and its plant stored."""
    context = await case_context(name)
    return context, await save_design(context, reference, example_plant(name, plant))


def depth_only(plant):
    """Return the plant with only its depth and doublets left as ranges, for a tiny search."""
    for path in list(plant.ranges):
        if path not in ("depth", "size.doublets"):
            plant.set_range(path, None, None)
    return plant


def one_range(plant):
    """Return the plant with only its heat pump capacity left as a range, for a tiny search."""
    for path in list(plant.ranges):
        if path != "heat_pump.capacity":
            plant.set_range(path, None, None)
    return plant


async def run(tool, context, tool_input):
    """Call a tool on a context and return its output, which must be plain JSON."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall

    result = await dispatch(tool, ToolCall(id="c1", name=tool.name, input=tool_input), context)
    json.dumps(result.output, allow_nan=False)
    return result


async def compare_two_runs():
    """Return ``(references, result)`` of ``compare`` on the shallow plant, unsized and sized."""
    import gemini as gm

    context, _ = await started(SHALLOW)
    case = study.case_of(context)
    plant = example_plant(SHALLOW)
    cheaper = study.size_design(plant, case)
    references = []
    for design in (plant, cheaper):
        results = gm.simulate(design, case)
        stored = await save_run(context, design, results, {"steps": 1}, {}, ran_case(context))
        references.append(stored)
    result = await run(study.compare, context, {"references": references, "by": ["lcts"]})
    return references, result


async def shallow_calls():
    """Return the search, the sizing and the two-design study on the shallow case."""
    context, reference = await started(SHALLOW)
    capacity = await save_design(context, "capacity", one_range(example_plant(SHALLOW)))
    arguments = {"objective": "lcts", "evaluations": 5, "seed": 1, "name": "best"}
    search = await run(study.optimize, context, {"design": capacity, **arguments})
    sized = await run(study.size_plant, context, {"design": reference, "name": "sized"})
    designs = [reference, sized.output["design"]]
    ranked = await run(
        study.run_study, context, {"designs": designs, "method": "run", "metrics": ["lcts"]}
    )
    return {"search": search, "sized": sized, "shallow": ranked}


async def hackathon_calls():
    """Return the sized and searched pair of topologies and the draws of the uncertain case."""
    context, _ = await started("hackathon_2026", "HeatingPlant", "heating")
    heating = await save_design(
        context, "heating", depth_only(example_plant("hackathon_2026", "HeatingPlant"))
    )
    pump = await save_design(
        context, "pump", depth_only(example_plant("hackathon_2026", HEAT_PUMP))
    )
    search = {"objective": "lcts", "evaluations": 5, "seed": 0, "prepare": ["size"]}
    smoke = await run(
        study.run_study,
        context,
        {"designs": [heating, pump], "method": "minimize", **search},
    )
    arguments = {"design": heating, "metrics": ["lcts"]}
    drawn = await run(study.sample_uncertainty, context, {**arguments, "samples": 3, "seed": 1})
    tornado = await run(study.sensitivity, context, arguments)
    return {"smoke": smoke, "drawn": drawn, "tornado": tornado, "context": context}


async def search_and_study():
    """Return every call that simulates, by name."""
    return {**await shallow_calls(), **await hackathon_calls()}


@functools.cache
def slow_calls():
    """Return the calls that simulate, run once per process outside the timed calls."""
    return {"studies": asyncio.run(search_and_study()), "compare": asyncio.run(compare_two_runs())}


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run the slow study calls before the tests read them."""
    slow_calls()


def test_size_plant_stores_the_sized_design():
    """A sized plant is a new design, with gemini's notes in readable quantities."""
    sized = slow_calls()["studies"]["sized"]
    assert sized.output["design"] == "design/sized"
    assert sized.output["sizing"]["sized"]


async def test_size_plant_takes_no_backup_argument():
    """The backup policy is the plant's, so the argument is not accepted."""
    context, reference = await started(SHALLOW)
    result = await run(
        study.size_plant, context, {"design": reference, "backup": "peak", "name": "s"}
    )
    assert result.is_error


async def test_size_plant_without_a_case_asks_for_one():
    """A state without a case is the case tools' message."""
    from geomind.context import ProblemState
    from geomind.engine import Context

    context, reference = await started(SHALLOW)
    bare = Context(session=context.session, problem=ProblemState())
    result = await run(study.size_plant, bare, {"design": reference, "name": "s"})
    assert result.is_error
    assert "set_case" in json.dumps(result.output)


def test_optimize_returns_a_feasible_best_in_display_units():
    """A tiny search over the design's ranges returns a feasible best and the trials."""
    output = slow_calls()["studies"]["search"].output
    assert output["feasible"]
    assert output["design"] == "design/best"
    assert output["trials"] >= 5
    assert output["best"]["plant"] is not None


async def test_optimize_without_ranges_is_gemini_error():
    """A design with no range or option has nothing to search: gemini's error."""
    from geomind.tools.gemini.stored import load_design

    context, reference = await started(SHALLOW)
    plant = load_design(context, reference, "test")
    for path in list(plant.ranges):
        plant.set_range(path, None, None)
    bare = await save_design(context, "bare", plant)
    result = await run(
        study.optimize,
        context,
        {"design": bare, "objective": "lcts", "evaluations": 5, "seed": 1, "name": "b"},
    )
    assert result.is_error


async def test_optimize_an_unknown_objective_is_gemini_error():
    """The objective is checked by gemini."""
    context, reference = await started(SHALLOW)
    result = await run(
        study.optimize,
        context,
        {"design": reference, "objective": "nonsense", "evaluations": 5, "seed": 1, "name": "b"},
    )
    assert result.is_error
    assert "nonsense" in json.dumps(result.output)


async def test_optimize_takes_no_variables():
    """The ranges are the design's: a list of variables is not accepted."""
    context, reference = await started(SHALLOW)
    arguments = {"design": reference, "objective": "lcts", "evaluations": 5, "seed": 1}
    result = await run(study.optimize, context, {**arguments, "name": "b", "variables": []})
    assert result.is_error


async def test_sample_uncertainty_needs_an_uncertainty_in_the_case():
    """A case without uncertainty is gemini's missing_value."""
    context, reference = await started(SHALLOW)
    result = await run(
        study.sample_uncertainty,
        context,
        {"design": reference, "metrics": ["lcts"], "samples": 3, "seed": 1},
    )
    assert result.is_error
    assert "missing_value" in json.dumps(result.output)


def test_sample_uncertainty_summarises_the_draws():
    """With an uncertain price the summary has the percentiles and the failed count."""
    summary = slow_calls()["studies"]["drawn"].output["summary"]["lcts"]
    assert {"mean", "p5", "p50", "p95", "failed"} <= set(summary)


def test_sensitivity_ranks_the_uncertain_values():
    """The tornado has rows for the metric."""
    rows = slow_calls()["studies"]["tornado"].output["rows"]
    assert rows[0]["metric"] == "lcts"


def test_run_study_ranks_the_designs_in_display_units():
    """A study of method run over two designs ranks them and stores what each ended with."""
    output = slow_calls()["studies"]["shallow"].output
    assert [item["plant_name"] for item in output["runs"]] == ["start", "sized"]
    assert output["runs"][0]["metrics"]["lcts"]["unit"] == "EUR/MWh"
    assert {item["ranks"]["lcts"] for item in output["runs"]} <= {1, 2}
    assert output["runs"][0]["design"] == "design/start_best"


def test_run_study_searches_two_topologies_of_the_hackathon():
    """The smoke test: two plant files, sized and searched on a tiny budget, each stored."""
    studies = slow_calls()["studies"]
    output = studies["smoke"].output
    assert [item["plant_name"] for item in output["runs"]] == ["heating", "pump"]
    assert all(item["found"]["evaluations"] for item in output["runs"])
    for item in output["runs"]:
        assert studies["context"].session.load_artifact(item["design"]) is not None


async def test_run_study_without_the_settings_the_method_needs_is_gemini_error():
    """A search with no seed has no default: gemini's missing issue."""
    context, reference = await started(SHALLOW)
    result = await run(
        study.run_study,
        context,
        {"designs": [reference], "method": "minimize", "objective": "lcts", "evaluations": 5},
    )
    assert result.is_error
    assert "seed" in json.dumps(result.output)


async def test_run_study_an_unknown_design_is_unknown_name():
    """A design no tool returned says so."""
    context, _ = await started(SHALLOW)
    result = await run(study.run_study, context, {"designs": ["design/none"], "method": "run"})
    assert result.is_error


def test_compare_ranks_two_runs():
    """Two stored runs, the sized and the unsized plant, come back ranked with their references."""
    references, result = slow_calls()["compare"]
    assert [entry["reference"] for entry in result.output] == references
    assert result.output[0]["values"]["lcts"]["unit"] == "EUR/MWh"
    assert {entry["ranks"]["lcts"] for entry in result.output} <= {1, 2}


async def test_compare_an_unknown_run_is_unknown_name():
    """A reference no run returned says so."""
    context, _ = await started(SHALLOW)
    result = await run(study.compare, context, {"references": ["result/none"], "by": ["lcts"]})
    assert result.is_error


def test_the_study_tools_have_a_time_limit():
    """A long search gives a timeout result instead of holding the run."""
    for name in ("size_plant", "optimize", "sample_uncertainty", "sensitivity", "run_study"):
        assert getattr(study, name).timeout == study.STUDY_TIMEOUT_S


@example_names
async def test_size_plant_on_each_example(name):
    """Sizing works on both examples with the plant's own backup policy."""
    context, reference = await started(name)
    result = await run(study.size_plant, context, {"design": reference, "name": "s"})
    assert result.output["sizing"]["sized"]
