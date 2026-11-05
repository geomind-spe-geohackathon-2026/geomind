"""The study tools over gemini's example cases: size, search, sample, run and compare."""

import asyncio
import copy
import functools
import json

import pytest

from geomind.tools.gemini import studies, study
from geomind.tools.gemini.case import case_of
from geomind.tools.gemini.stored import ran_case, save_design, save_run, save_study
from tests.fixtures.cases import engine_context, example_names, example_plant

SHALLOW = "shallow_district"
HEAT_PUMP = "HeatingHeatPumpCoolingPlant"


async def started(name, plant=None, reference="start"):
    """Return ``(context, design reference)``: the example's case and its plant stored."""
    context, _ = await engine_context(name)
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
    case = case_of(context)
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
        study.run_study,
        context,
        {"designs": designs, "method": "run", "metrics": ["lcts"], "name": "pair"},
    )
    again = {"designs": [reference], "method": "run", "prepare": ["size"], "name": "sizedrun"}
    return {
        "search": search,
        "sized": sized,
        "shallow": ranked,
        "again": await run(study.run_study, context, again),
        "shallow_context": context,
        **await rejected_calls(context),
    }


def without_ranges(plant, kept=()):
    """Return the plant with every range removed except the paths in ``kept``."""
    for path in list(plant.ranges):
        if path not in kept:
            plant.set_range(path, None, None)
    return plant


async def rejected_calls(context):
    """Return the calls gemini rejects for a missing range: a sizing, a study and a search."""
    plant = without_ranges(example_plant(SHALLOW), kept=("depth",))
    open_doublets = await save_design(context, "nodoublets", plant)
    bare = await save_design(context, "bare", without_ranges(example_plant(SHALLOW)))
    sizing = await run(study.size_plant, context, {"design": open_doublets, "name": "s2"})
    prepared = {"designs": [open_doublets], "method": "run", "prepare": ["size"], "name": "s3"}
    searching = {"objective": "lcts", "evaluations": 5, "seed": 1, "name": "s4"}
    return {
        "unsized": sizing,
        "unsized_study": await run(study.run_study, context, prepared),
        "unsearched": await run(study.optimize, context, {"design": bare, **searching}),
    }


async def hackathon_calls():
    """Return the sized and searched pair of topologies and the draws of the uncertain case."""
    context, _ = await started("hackathon_2026", "HeatingPlant", "plain")
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
        {"designs": [heating, pump], "method": "minimize", "name": "families", **search},
    )
    arguments = {"design": heating, "metrics": ["lcts"]}
    draws = {**arguments, "samples": 3, "seed": 1, "name": "draws"}
    drawn = await run(study.sample_uncertainty, context, draws)
    tornado = await run(study.sensitivity, context, {**arguments, "name": "tornado"})
    named = {**arguments, "name": "named", "values": ["economics.discount_rate"]}
    one = await run(study.sensitivity, context, named)
    wrong = {**arguments, "name": "wrong", "values": ["economics.capex.drilling"]}
    undeclared = await run(study.sensitivity, context, wrong)
    return {
        "smoke": smoke,
        "drawn": drawn,
        "tornado": tornado,
        "named": one,
        "undeclared": undeclared,
        "context": context,
    }


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
        {"design": reference, "metrics": ["lcts"], "samples": 3, "seed": 1, "name": "d"},
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


def test_a_sensitivity_of_named_values_moves_only_those():
    """values keeps the named uncertainty; a value the case declares none for is refused."""
    studies = slow_calls()["studies"]
    rows = studies["named"].output["rows"]
    assert {row["parameter"] for row in rows} == {"case.economics.discount_rate"}
    refused = studies["undeclared"]
    assert refused.is_error and "economics.discount_rate" in refused.output["error"]["message"]


def test_run_study_ranks_the_designs_in_display_units():
    """A study of method run over two designs ranks them and stores what each ended with."""
    output = slow_calls()["studies"]["shallow"].output
    assert [item["plant_name"] for item in output["runs"]] == ["start", "sized"]
    assert output["runs"][0]["metrics"]["lcts"]["unit"] == "EUR/MWh"
    assert {item["ranks"]["lcts"] for item in output["runs"]} <= {1, 2}
    assert output["runs"][0]["design"] == "design/pair_start"


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
        {
            "designs": [reference],
            "method": "minimize",
            "objective": "lcts",
            "evaluations": 5,
            "name": "m",
        },
    )
    assert result.is_error
    assert "seed" in json.dumps(result.output)


async def test_run_study_an_unknown_design_is_unknown_name():
    """A design no tool returned says so."""
    context, _ = await started(SHALLOW)
    result = await run(
        study.run_study, context, {"designs": ["design/none"], "method": "run", "name": "n"}
    )
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
    assert (result.output["checked_against"], result.output["issues"]) == ("case", [])
    assert result.output["missing"] == 0


async def test_size_plant_names_what_simulate_still_needs():
    """fix-design note: size_plant gave no issues, so a sized plant without its rules failed later.

    The sized design comes with the issues and the count ``patch_plant`` gives.
    """
    import gemini as gm

    context, _ = await engine_context(SHALLOW)
    plant = example_plant(SHALLOW).to_dict()
    plant["params"].pop("control")
    reference = await save_design(context, "nocontrol", gm.Plant.from_dict(plant))
    result = await run(study.size_plant, context, {"design": reference, "name": "s"})
    paths = [issue["path"] for issue in result.output["issues"]]
    # IMP-019: the two rules gemini allows one value of are filled, so none is missing.
    assert "params.control.dispatch" not in paths and "params.control.outages" not in paths
    assert result.output["sizing"]["sized"]


def test_a_second_study_over_the_same_design_is_stored():
    """Each study stores its own designs, ``design/<study>_<plant>``, so a second is not refused.

    NOTE: before 0.4.0 both stored ``design/<plant>_best`` and the second call failed.
    """
    studies = slow_calls()["studies"]
    first, second = studies["shallow"].output, studies["again"].output
    assert not studies["again"].is_error
    assert first["runs"][0]["design"] == "design/pair_start"
    assert second["runs"][0]["design"] == "design/sizedrun_start"


STORED = {
    "sized": ("size_plant", "run", ["start"]),
    "search": ("optimize", "minimize", ["capacity"]),
    "drawn": ("sample_uncertainty", "sample", ["heating"]),
    "tornado": ("sensitivity", "sensitivity", ["heating"]),
    "shallow": ("run_study", "run", ["start", "sized"]),
    "smoke": ("run_study", "minimize", ["heating", "pump"]),
}
CONTEXT_OF = {"sized": "shallow_context", "search": "shallow_context", "shallow": "shallow_context"}


@pytest.mark.parametrize("call", STORED)
def test_every_study_tool_stores_its_study(call):
    """The result names ``study/<name>``, whose artifact is gemini's study file and its result."""
    studies = slow_calls()["studies"]
    tool_name, method, plants = STORED[call]
    key = studies[call].output["study"]
    context = studies[CONTEXT_OF.get(call, "context")]
    record = context.session.load_artifact(key)
    assert set(record) == {"study", "result", "designs", "case", "tool", "versions"}
    assert (record["tool"], record["study"]["method"]) == (tool_name, method)
    assert record["study"]["kind"] == "study" and record["study"]["name"] == key.split("/")[1]
    assert [design.split("/")[1] for design in record["study"]["plants"]] == plants
    assert record["designs"]["read"] == record["study"]["plants"]
    assert set(record["versions"]) == {"geomind", "gemini", "python"}


def test_a_run_study_keeps_gemini_result_and_the_designs_it_wrote():
    """The result is ``StudyResult.to_dict()`` and the wrote list names the stored designs."""
    studies = slow_calls()["studies"]
    record = studies["shallow_context"].session.load_artifact("study/pair")
    assert {"study", "runs", "comparison", "best"} <= set(record["result"])
    assert record["designs"]["wrote"] == ["design/pair_start", "design/pair_sized"]


def test_an_optimize_keeps_its_best_without_the_plant_and_recommends_it():
    """The design is stored apart; the study keeps gemini's best with ``plant`` left empty."""
    context = slow_calls()["studies"]["shallow_context"]
    record = context.session.load_artifact("study/best")
    assert record["result"]["best"]["plant"] is None
    assert record["designs"]["wrote"] == ["design/best"]


def test_an_optimize_keeps_the_history_of_its_search():
    """Every trial of gemini's search is kept, in gemini's own plain form."""
    context = slow_calls()["studies"]["shallow_context"]
    record = context.session.load_artifact("study/best")
    history = record["result"]["history"]
    assert len(history) == record["result"]["evaluations"]
    assert {"value", "unit", "parameters"} <= set(history[0])


async def test_a_taken_design_name_is_refused_with_its_name_before_the_study_runs():
    """``optimize`` and ``size_plant`` name the design that is taken, and nothing runs."""
    context, reference = await started(SHALLOW)
    result = await run(study.size_plant, context, {"design": reference, "name": "start"})
    assert result.is_error
    message = result.output["error"]["message"]
    assert "design/start" in message and "taken" in message
    assert result.output["error"]["path"] == "name"
    search = {"design": reference, "objective": "lcts", "evaluations": 20, "seed": 1}
    refused = await run(study.optimize, context, {**search, "name": "start"})
    assert "design/start" in refused.output["error"]["message"]
    assert context.session.load_artifact("studies.index") is None


def test_a_taken_study_name_is_refused():
    """Another study under the name of a stored one is refused; nothing is overwritten."""
    context = slow_calls()["studies"]["shallow_context"]
    reference = "design/start"
    refused = asyncio.run(run(study.size_plant, context, {"design": reference, "name": "pair"}))
    assert "study/pair" in refused.output["error"]["message"]


async def test_a_study_name_is_a_valid_design_name():
    """The name becomes part of design names, so it is checked first."""
    context, reference = await started(SHALLOW)
    result = await run(study.size_plant, context, {"design": reference, "name": "a b"})
    assert result.is_error and "name" in result.output["error"]["message"]


def test_list_studies_shows_each_study_and_whether_its_case_is_current():
    """The list has the key, tool, method, plants and best; a changed case makes it not current."""
    from geomind.context import ProblemState
    from geomind.engine import Context

    context = slow_calls()["studies"]["shallow_context"]
    listed = asyncio.run(run(studies.list_studies, context, {})).output
    pair = next(item for item in listed if item["study"] == "study/pair")
    assert pair == {
        "study": "study/pair",
        "tool": "run_study",
        "method": "run",
        "designs": ["start", "sized"],
        "best": pair["best"],
        "current": True,
    }
    assert all(item["current"] for item in listed)
    changed = copy.deepcopy(context.problem.case)
    changed["name"] = "another case"
    later = Context(session=context.session, problem=ProblemState(case=changed))
    assert not any(
        item["current"] for item in asyncio.run(run(studies.list_studies, later, {})).output
    )


def test_read_study_returns_the_stored_artifact_and_refuses_an_unknown_key():
    """The artifact comes back whole; a key no tool returned is ``unknown_name``."""
    context = slow_calls()["studies"]["shallow_context"]
    stored = asyncio.run(run(studies.read_study, context, {"study": "study/pair"})).output
    assert stored == context.session.load_artifact("study/pair")
    unknown = asyncio.run(run(studies.read_study, context, {"study": "study/none"}))
    assert unknown.output["error"]["code"] == "unknown_name"


async def test_study_recorded_is_sent_once_after_the_artifact_is_saved():
    """The event carries the fields of the contract and the artifact and index are saved first."""
    context, _ = await started(SHALLOW)
    session = context.session
    seen = []
    emit = session.emit

    async def checked(kind, **fields):
        seen.append((session.load_artifact("study/s"), session.load_artifact("studies.index")))
        return await emit(kind, **fields)

    session.emit = checked
    study_data = {"format": 1, "kind": "study", "name": "s", "method": "run"}
    context = context.for_call("c9")
    found = (study_data, {})
    key = await save_study(
        context, "s", "run_study", found, (["design/a"], ["design/s_a"]), None, "k"
    )
    events = [e for e in session.engine.store.events["r1"] if e.type == "study.recorded"]
    assert key == "study/s" and len(events) == 1 and len(seen) == 1
    assert seen[0][0] is not None and seen[0][1]["studies"][0]["study"] == "study/s"
    assert events[0].data() == {
        "run": "r1",
        "index": 0,
        "call_id": "c9",
        "study": "study/s",
        "tool": "run_study",
        "method": "run",
        "designs": ["a"],
        "agent": "worker",
        "parent": None,
    }


def test_size_plant_names_the_missing_range_and_the_call_that_adds_it():
    """The error keeps gemini's message, names the path and gives set_ranges without a number."""
    error = slow_calls()["studies"]["unsized"].output["error"]
    assert error["code"] == "missing_value"
    assert "size.doublets.range is missing" in error["message"]
    assert "set_ranges(design='design/nodoublets'" in error["message"]
    assert "'size.doublets': {'min': <min>, 'max': <max>}" in error["message"]
    assert "not in the case" in error["message"] and "ask_user" in error["message"]
    assert not any(character.isdigit() for character in error["message"].split("set_ranges")[1])


def test_run_study_with_prepare_size_names_the_missing_range():
    """A study that sizes first is rejected for the same range, with the same call."""
    error = slow_calls()["studies"]["unsized_study"].output["error"]
    assert "set_ranges(design='design/nodoublets'" in error["message"]


def test_optimize_with_no_range_lists_the_leaves_with_their_units():
    """A search over a plant with nothing to search names leaves and units, and the call."""
    error = slow_calls()["studies"]["unsearched"].output["error"]
    assert error["code"] == "invalid_design"
    assert "depth [m]" in error["message"]
    assert "ask_user" in error["message"] and "confirm" in error["message"]
    assert "set_ranges(design='design/bare'" in error["message"]


def test_the_study_tools_offer_the_reference_pattern_with_an_example():
    """Each argument that takes a stored reference has a pattern and one example."""
    properties = study.size_plant.schema()["input_schema"]["properties"]
    assert properties["design"]["pattern"] == "^design/[A-Za-z0-9._-]+$"
    assert "design/boiler_only" in properties["design"]["description"]
    items = study.run_study.schema()["input_schema"]["properties"]["designs"]["items"]
    assert items["pattern"] == "^design/[A-Za-z0-9._-]+$"
    results = study.compare.schema()["input_schema"]["properties"]["references"]["items"]
    assert results["pattern"] == "^result/[A-Za-z0-9._-]+$"


async def test_size_plant_with_a_name_without_its_prefix_lists_the_stored_designs():
    """The model's ``hphp2`` gets the designs of the chat and the form it meant."""
    context, _ = await started(SHALLOW, reference="hphp2")
    result = await run(study.size_plant, context, {"design": "hphp2", "name": "n"})
    message = result.output["error"]["message"]
    assert result.output["error"]["code"] == "unknown_name"
    assert "stored design references: design/hphp2" in message
    assert "did you mean 'design/hphp2'" in message


def test_the_range_tools_say_ranges_come_from_the_user_or_the_case():
    """set_ranges and the uncertainty studies tell the agent not to invent a range."""
    from geomind.tools.gemini.plants import set_ranges

    assert "from the user or the case" in set_ranges.description
    assert "ask_user" in set_ranges.description
    for tool in (study.sample_uncertainty, study.sensitivity):
        assert "from the user or the case" in tool.description


class FakeDesign(dict):
    """A design of gemini's evolution, as ``evolve_structure`` reads it."""

    def to_dict(self):
        """Return the plain form, as gemini's ``Design.to_dict``."""
        return {**self, "plant": "plant dict", "parameters": {"x": 1}}


class FakeEvolution(dict):
    """gemini's ``Evolution`` with a front of two designs."""

    def to_dict(self):
        """Return the plain form, as gemini's ``Evolution.to_dict``."""
        return {
            "front": [item.to_dict() for item in self["front"]],
            "best": self["best"].to_dict(),
            "history": [],
            "structures": [],
            "rejected": self.get("rejected", []),
            "budget": {"stopped": self.get("stopped", "budget")},
            "evaluations": self["evaluations"],
            "invalid": self["invalid"],
        }

    def explain(self):
        """Return gemini's short text of the search."""
        return "Objectives: lcts."

    def to_frame(self):
        """Return the front as gemini's table: a column per structure key and metric."""
        import pandas as pd

        return pd.DataFrame(
            [
                {**item["structure"], "lcts [EUR/MWh]": item["metrics"]["lcts"]}
                | {"feasible": item["feasible"], "reason": item["reason"]}
                for item in self["front"]
            ]
        )


def front_of(context, reference):
    """Return two designs of a front on the stored plant: one feasible, one not."""
    from geomind.tools.gemini.stored import load_design

    plant = load_design(context, reference, "test")
    first = FakeDesign(
        structure={"boiler": True}, plant=plant, metrics={"lcts": 1.0}, feasible=True, reason=None
    )
    second = FakeDesign(
        structure={"boiler": False},
        plant=plant,
        metrics={"lcts": 2.0},
        feasible=False,
        reason="unmet heat",
    )
    return first, second


async def test_evolve_structure_stores_each_design_of_the_front(monkeypatch):
    """The front comes back compact, every design stored, the study recorded; gemini computes."""
    context, reference = await started(SHALLOW)
    first, second = front_of(context, reference)
    found = FakeEvolution(front=[first, second], best=first, evaluations=40, invalid=1)
    calls = []

    def fake(*arguments):
        calls.append(arguments)
        return found

    monkeypatch.setattr("geomind.tools.gemini.study.evolve_design", fake)
    arguments = {"design": reference, "objectives": ["lcts"], "name": "evo"}
    result = await run(study.evolve_structure, context, arguments)
    output = result.output
    assert not result.is_error, output
    assert [item["design"] for item in output["front"]] == ["design/evo_1", "design/evo_2"]
    assert output["best"] == "design/evo_1" and output["study"] == "study/evo"
    assert output["front"][1] == {
        "design": "design/evo_2",
        "structure": {"boiler": False},
        "metrics": {"lcts": 2.0},
        "feasible": False,
        "reason": "unmet heat",
    }
    assert calls[0][2] == ["lcts"]
    assert calls[0][3] == {
        "evaluations": 40,
        "population": 8,
        "seed": 0,
        "polish": 0,
        "stop": {"generations": 5},
    }
    assert output["stopped"] == "budget" and "40 simulations" in output["why"]


async def test_evolve_structure_keeps_gemini_s_explanation_and_table(monkeypatch):
    """The stored study carries ``explain()`` and ``to_frame()`` as gemini gives them."""
    context, reference = await started(SHALLOW)
    first, second = front_of(context, reference)
    found = FakeEvolution(front=[first, second], best=first, evaluations=40, invalid=0)
    monkeypatch.setattr("geomind.tools.gemini.study.evolve_design", lambda *arguments: found)
    arguments = {"design": reference, "objectives": ["lcts"], "name": "evo"}
    output = (await run(study.evolve_structure, context, arguments)).output
    stored = (await run(studies.read_study, context, {"study": output["study"]})).output["result"]
    assert stored["explanation"] == "Objectives: lcts."
    assert stored["table"] == {
        "columns": ["boiler", "lcts [EUR/MWh]", "feasible", "reason"],
        "rows": [[True, 1.0, True, None], [False, 2.0, False, "unmet heat"]],
    }
    json.dumps(stored)


@pytest.mark.parametrize(
    ("generations", "seconds", "stop"),
    [
        ("off", "off", None),
        (3, "off", {"generations": 3}),
        ("off", 60.0, {"seconds": 60.0}),
        (3, 60.0, {"generations": 3, "seconds": 60.0}),
    ],
)
def test_the_stop_settings_give_gemini_s_stop(generations, seconds, stop):
    """Each stop setting is a number or off; both off spend the whole budget (``stop=None``)."""
    from geomind import runtime

    with runtime.settings(evolve_stop_generations=generations, evolve_stop_seconds=seconds):
        assert study.evolve_settings()["stop"] == stop


@pytest.mark.parametrize(
    ("stopped", "words"),
    [
        ("budget", "40 simulations of GEOMIND_EVOLVE_EVALUATIONS"),
        ("stalled", "no new candidate"),
        ("converged", "for 5 generations in a row (GEOMIND_EVOLVE_STOP_GENERATIONS)"),
        ("seconds", "60.0 s (GEOMIND_EVOLVE_STOP_SECONDS)"),
    ],
)
def test_why_the_search_stopped_is_said_in_words(stopped, words):
    """``why`` names the setting that ended the search, with its value."""
    settings = {"evaluations": 40, "stop": {"generations": 5, "seconds": 60.0}}
    assert words in study.stop_reason(stopped, settings)


async def test_evolve_structure_says_which_structures_gemini_refused(monkeypatch):
    """The structures gemini 0.6.2 refused (``rejected``, a port left open) and why it stopped."""
    context, reference = await started(SHALLOW)
    first, _ = front_of(context, reference)
    refused = {"structure": {"boiler": False, "cooling": "off"}, "reasons": ["port open"]}
    found = FakeEvolution(front=[first], best=first, evaluations=4, invalid=0, rejected=[refused])
    monkeypatch.setattr("geomind.tools.gemini.study.evolve_design", lambda *arguments: found)
    arguments = {"design": reference, "objectives": ["lcts"], "name": "evo"}
    output = (await run(study.evolve_structure, context, arguments)).output
    assert output["rejected"] == [refused] and output["stopped"] == "budget"


async def test_evolve_structure_needs_its_settings():
    """The evaluations, population, seed, polish and stops have no default: unset, each is named."""
    from geomind import runtime

    context, reference = await started(SHALLOW)
    with runtime.settings(evolve_population=None, evolve_polish=None, evolve_stop_seconds=None):
        result = await run(
            study.evolve_structure,
            context,
            {"design": reference, "objectives": ["lcts"], "name": "evo"},
        )
    message = result.output["error"]["message"]
    assert result.is_error and "GEOMIND_EVOLVE_POPULATION" in message
    assert "GEOMIND_EVOLVE_POLISH" in message and "GEOMIND_EVOLVE_STOP_SECONDS" in message


@pytest.mark.slow
async def test_evolve_structure_runs_gemini_s_search_on_a_superstructure():
    """A real, small search: a choice between two backup groups, a front from gemini."""
    from geomind import runtime
    from geomind.tools.gemini.stored import load_design

    context, reference = await started(SHALLOW)
    plant = load_design(context, reference, "test")
    names = sorted(plant.to_dict(structure=True)["modules"])
    optional = next(name for name in names if "boiler" in name or "storage" in name)
    plant.set_optional(optional)
    superstructure = await save_design(context, "super", plant)
    with runtime.settings(evolve_evaluations=4, evolve_population=2, evolve_polish=0):
        result = await run(
            study.evolve_structure,
            context,
            {"design": superstructure, "objectives": ["lcts"], "name": "evo"},
        )
    assert not result.is_error, result.output
    assert result.output["front"] and result.output["evaluations"] >= 1
    assert result.output["stopped"] and result.output["why"]
    stored = (await run(studies.read_study, context, {"study": result.output["study"]})).output[
        "result"
    ]
    assert stored["explanation"].startswith("Objectives: lcts")
    assert stored["table"]["rows"] and json.dumps(stored)
