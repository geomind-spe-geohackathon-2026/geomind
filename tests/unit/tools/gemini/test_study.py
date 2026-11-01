"""The study tools over gemini's example cases: size, search, sample, sensitivity and compare."""

import json

import pytest

from geomind.tools.gemini import study
from geomind.tools.gemini.stored import save_design, save_run
from tests.fixtures.cases import case_context, example_names, example_plant

UNCERTAIN = {
    "assumptions": {
        "finance": {
            "opex": {
                "electricity": {
                    "value": 120,
                    "unit": "EUR/MWh",
                    "uncertainty": {"kind": "uniform", "min": 90, "max": 150},
                }
            }
        }
    }
}


async def started(name):
    """Return ``(context, design reference)``: the example's case and its passing plant stored."""
    context = await case_context(name)
    reference = await save_design(context, "start", example_plant(name))
    return context, reference


async def run(tool, context, tool_input):
    """Call a tool on a context and return its output, which must be plain JSON."""
    from geomind.tools import dispatch
    from geomind.types import ToolCall

    result = await dispatch(tool, ToolCall(id="c1", name=tool.name, input=tool_input), context)
    json.dumps(result.output, allow_nan=False)
    return result


def bounds(name, parameter, low, high, unit):
    """Return one variable of a search."""
    return {
        "path": name,
        "parameter": parameter,
        "lower": {"value": low, "unit": unit},
        "upper": {"value": high, "unit": unit},
    }


@example_names
@pytest.mark.parametrize("backup", ["peak", "none"])
async def test_size_plant_stores_the_sized_design(name, backup):
    """A sized plant is a new design, with gemini's notes in readable quantities."""
    context, reference = await started(name)
    result = await run(
        study.size_plant, context, {"design": reference, "backup": backup, "name": "s"}
    )
    assert result.output["design"] == "design/s"
    assert result.output["sizing"]["sized"]
    assert context.session.load_artifact("design/s") is not None


async def test_size_plant_needs_the_policy():
    """The backup policy has no default."""
    context, reference = await started("shallow_district")
    result = await run(study.size_plant, context, {"design": reference, "name": "s"})
    assert result.is_error


async def test_size_plant_without_a_case_asks_for_one():
    """A state without a case is the case tools' message."""
    from geomind.context import ProblemState
    from geomind.engine import Context

    context, reference = await started("shallow_district")
    bare = Context(session=context.session, problem=ProblemState())
    result = await run(study.size_plant, bare, {"design": reference, "backup": "peak", "name": "s"})
    assert result.is_error
    assert "set_case" in json.dumps(result.output)


async def test_optimize_stores_a_feasible_best():
    """A tiny search on the shallow case returns a feasible best and stores it."""
    context, reference = await started("shallow_district")
    result = await run(
        study.optimize,
        context,
        {
            "design": reference,
            "objective": "lcts",
            "variables": [bounds("", "depth", 1100, 1500, "m")],
            "evaluations": 5,
            "name": "best",
        },
    )
    assert result.output["feasible"]
    assert result.output["design"] == "design/best"
    assert result.output["trials"] >= 5
    assert context.session.load_artifact("design/best") is not None


async def test_optimize_with_no_variables_searches_the_choices_of_the_case():
    """An empty list is the case's choices, which the shallow case declares."""
    context, reference = await started("shallow_district")
    result = await run(
        study.optimize,
        context,
        {"design": reference, "objective": "lcts", "variables": [], "evaluations": 10, "name": "b"},
    )
    assert result.output["best"]["parameters"]


async def test_optimize_an_unknown_objective_is_gemini_error():
    """The objective is checked by gemini."""
    context, reference = await started("shallow_district")
    result = await run(
        study.optimize,
        context,
        {
            "design": reference,
            "objective": "nonsense",
            "variables": [bounds("", "depth", 1100, 1500, "m")],
            "evaluations": 5,
            "name": "b",
        },
    )
    assert result.is_error
    assert "nonsense" in json.dumps(result.output)


async def test_optimize_a_wrong_variable_path_is_gemini_error():
    """A variable on a path nobody has comes back as gemini's problem."""
    context, reference = await started("shallow_district")
    result = await run(
        study.optimize,
        context,
        {
            "design": reference,
            "objective": "lcts",
            "variables": [bounds("nowhere", "capacity", 1, 2, "MW")],
            "evaluations": 5,
            "name": "b",
        },
    )
    assert result.is_error


async def test_sample_uncertainty_needs_an_uncertainty_in_the_case():
    """A case without uncertainty is gemini's missing_value."""
    context, reference = await started("shallow_district")
    result = await run(
        study.sample_uncertainty,
        context,
        {"design": reference, "metrics": ["lcts"], "count": 3, "seed": 1},
    )
    assert result.is_error
    assert "missing_value" in json.dumps(result.output)


async def declared(name):
    """Return ``(context, design)`` with an uncertain electricity price added through set_case."""
    from geomind.context import ProblemState
    from geomind.engine import Context
    from geomind.tools.gemini import set_case

    context, reference = await started(name)
    await run(set_case, context, {"changes": UNCERTAIN})
    case = context.session.changes[-1][0]["value"]
    return Context(session=context.session, problem=ProblemState(case=case)), reference


async def test_sample_uncertainty_summarises_the_draws():
    """With an uncertain price the summary has the percentiles and the failed count."""
    context, reference = await declared("shallow_district")
    result = await run(
        study.sample_uncertainty,
        context,
        {"design": reference, "metrics": ["lcts"], "count": 3, "seed": 1},
    )
    summary = result.output["summary"]["lcts"]
    assert {"mean", "p5", "p50", "p95", "failed"} <= set(summary)


async def test_sensitivity_ranks_the_uncertain_values():
    """The tornado has an item for the uncertain price."""
    context, reference = await declared("shallow_district")
    result = await run(study.sensitivity, context, {"design": reference, "metrics": ["lcts"]})
    assert result.output["rows"][0]["metric"] == "lcts"
    assert "electricity" in result.output["rows"][0]["parameter"]


async def test_compare_ranks_two_runs():
    """Two stored runs, the sized and the unsized plant, come back ranked with their references."""
    import gemini as gm

    context, _ = await started("shallow_district")
    case = study.case_of(context)
    plant = example_plant("shallow_district")
    cheaper = study.size_design(plant, case, "peak")
    references = []
    for design in (plant, cheaper):
        results = gm.simulate(design, case)
        references.append(await save_run(context, design, results, {"steps": 1}, {}))
    result = await run(study.compare, context, {"references": references, "by": ["lcts"]})
    assert [entry["reference"] for entry in result.output] == references
    assert result.output[0]["values"]["lcts"]["unit"] == "EUR/MWh"
    assert {entry["ranks"]["lcts"] for entry in result.output} <= {1, 2}


async def test_compare_an_unknown_run_is_unknown_name():
    """A reference no run returned says so."""
    context, _ = await started("shallow_district")
    result = await run(study.compare, context, {"references": ["result/none"], "by": ["lcts"]})
    assert result.is_error


@pytest.mark.slow
async def test_hackathon_size_then_optimize():
    """The hackathon case: size, then a tiny search on depth."""
    context, reference = await started("hackathon_2026")
    sized = await run(
        study.size_plant, context, {"design": reference, "backup": "peak", "name": "s"}
    )
    searched = await run(
        study.optimize,
        context,
        {
            "design": sized.output["design"],
            "objective": "lcts",
            "variables": [bounds("", "depth", 2000, 3000, "m")],
            "evaluations": 5,
            "name": "b",
        },
    )
    assert searched.output["design"] == "design/b"
