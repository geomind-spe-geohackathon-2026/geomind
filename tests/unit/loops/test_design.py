"""``DesignLoop``: propose, simulate, verify, route the failures by domain, and repeat."""

import json
from pathlib import Path

import pytest

from geomind.agents import Designer, Verifier
from geomind.context import ProblemState
from geomind.engine import Context, Engine
from geomind.engine.hooks import Verified
from geomind.engine.recovery import recover
from geomind.loops import DesignLoop
from geomind.loops.design import (
    DesignDriver,
    economist_task,
    repeated,
    request_of,
    routed_task,
)
from geomind.stores import MemoryWorkspace
from geomind.types import Message
from tests.fixtures.cases import example_case
from tests.fixtures.runs import call, context, engine_for, logged, of_type, same_usage, says, uses
from tests.fixtures.sessions import StubSession

FAILED = {
    "passed": False,
    "checks": [],
    "failures": [
        {
            "name": "heat_users.supply_in.temperature",
            "domain": "surface",
            "detail": "339.45 K against 373.15 K",
        },
        {"name": "d0.flow", "domain": "subsurface", "detail": "0.1 m3/s against 0.0833 m3/s"},
        {"name": "heat_users.unmet", "domain": "sizing", "detail": "2 MW against 0 MW"},
        {"name": "plant energy", "domain": "coupled", "detail": "0.1 - against 1e-06 -"},
    ],
}
PASSED = {"passed": True, "checks": [], "failures": []}
CASE = {
    "time": {"start": "2026-01-01", "end": "2026-01-03", "step": {"value": 1, "unit": "d"}},
    "demand": {"file": "demand.csv", "heating": {"column": "heat", "unit": "MW"}},
}
NO_DEMAND = {"time": CASE["time"], "choices": {}}


@pytest.fixture
def verdicts(monkeypatch):
    """Return the list of gemini's verdicts the loop and the ``Verified`` hook read, in order."""
    queue = []

    def verdict(_):
        return queue[0] if len(queue) == 1 else queue.pop(0)

    monkeypatch.setattr("geomind.loops.design.verify_design", verdict)
    monkeypatch.setattr("geomind.engine.hooks.verify_design", lambda _: PASSED)
    return queue


def designer_round(index):
    """Return the designer's completions: record the final design and its result, hand over."""
    record = {"op": "replace", "path": "/design", "value": design_of(index)}
    return [uses(call("update_state", f"u{index}", changes=[record])), says(f"design {index}")]


def design_of(index):
    """Return the design the designer of round ``index`` records."""
    return {"reference": f"design/d{index}", "result": f"result/r{index}"}


def verifier_round(index):
    """Return the verifier's completions: check the recorded result, record it, report."""
    result = f"result/r{index}"
    record = {"op": "replace", "path": "/verification", "value": {"result": result}}
    return [
        uses(call("check_results", f"vc{index}", reference=result)),
        uses(call("update_state", f"vu{index}", changes=[record])),
        says("checked"),
    ]


async def run_loop(completions, case=CASE, max_rounds=5, origin=None):
    """Run a design loop on scripted completions; return the result and the events."""
    engine = engine_for(completions)
    problem = ProblemState(case=case, case_origin=origin)
    start = context("Design the plant of the case.", problem=problem)
    result = await DesignLoop(Designer(), Verifier(), max_rounds=max_rounds).run(engine, start)
    return result, engine, engine.store.load_events(start.run_id)


def tasks_of(events, agent):
    """Return the tasks the loop gave one agent, in order."""
    return [e.messages[0].content for e in of_type(events, "run.started") if e.agent == agent]


def agents_of(events):
    """Return the agents the loop ran, in order, without the root run."""
    return [e.agent for e in of_type(events, "run.started")][1:]


def test_the_constructor_is_final():
    """Two agents and a limit; the run starts with a driver whose first move is the designer."""
    first = Designer()
    loop = DesignLoop(designer=first, verifier=Verifier())
    assert (loop.name, loop.max_rounds) == ("design", 5)
    assert isinstance(loop.agent, DesignDriver)
    assert loop.agent.tools()["designer"].agent is first


def test_a_task_routes_each_failure_to_its_side():
    """Subsurface, surface, resizing and coupled failures each get their own instruction."""
    task = routed_task(2, 5, "design/a", "result/r", FAILED)
    assert task.index("Subsurface side") < task.index("d0.flow")
    assert task.index("Surface side") < task.index("heat_users.supply_in.temperature")
    assert task.index("Resize") < task.index("heat_users.unmet")
    assert "subsurface first, then the surface" in task
    assert "339.45 K against 373.15 K" in task and "stale" in task


def test_the_same_failures_twice_are_repeated():
    """The loop stops when one round fails exactly as the one before."""
    assert repeated([["a", "b"], ["b", "a"]])
    assert not repeated([["a"], ["a", "b"]])
    assert not repeated([["a"]])


async def test_a_design_that_passes_goes_to_the_economist_then_the_explainer(verdicts):
    """The verifier checks the final design once; a pass is costed, explained and answered."""
    verdicts.append(PASSED)
    script = [
        *designer_round(1),
        *verifier_round(1),
        says("capex 41 MEUR"),
        says("## Design\nTwo doublets."),
    ]
    result, engine, events = await run_loop(script)
    assert (result.status, result.stop_reason) == ("done", "finish")
    assert "## Design\nTwo doublets." in result.answer
    assert agents_of(events) == ["designer", "verifier", "economist", "explainer"]
    assert "result/r1" in tasks_of(events, "verifier")[0]
    assert "design/d1" in tasks_of(events, "economist")[0]
    assert any(isinstance(hook, Verified) for hook in engine.hooks())
    assert "stop: verified" in of_type(events, "run.finished")[-1].answer
    assert same_usage(result.usage, logged(events)) and result.usage.input_tokens > 0


async def test_a_verifier_failure_sends_its_routed_failures_to_the_designer(verdicts):
    """Round 2 is told gemini's failures by domain; the pass of round 2 goes on to the costs."""
    verdicts.extend([FAILED, PASSED])
    script = [
        *designer_round(1),
        *verifier_round(1),
        *designer_round(2),
        *verifier_round(2),
        says("costs"),
        says("explained"),
    ]
    result, _, events = await run_loop(script)
    second = tasks_of(events, "designer")[1]
    assert result.status == "done"
    assert agents_of(events) == [
        *["designer", "verifier"] * 2,
        "economist",
        "explainer",
    ]
    assert "Round 2 of at most 5" in second
    assert second.index("Surface side") < second.index("heat_users.supply_in.temperature")
    assert second.index("Subsurface side") < second.index("d0.flow")
    assert "339.45 K against 373.15 K" in second


async def test_the_round_limit_stops_without_presenting_a_design(verdicts):
    """A design that never passes is moved to ``design.rejected``, and the answer says why."""
    verdicts.append(FAILED)
    script = [*designer_round(1), *verifier_round(1)]
    result, _, events = await run_loop(script, max_rounds=1)
    problem = recover(events).problem
    assert result.status == "done"
    assert "stop: max_rounds" in result.answer
    assert "reference" not in problem.design
    assert problem.design["rejected"] == ["design/d1"]


async def test_the_same_failures_twice_stop_the_loop(verdicts):
    """Two rounds that fail alike end the loop before the round limit."""
    verdicts.append(FAILED)
    script = [
        *designer_round(1),
        *verifier_round(1),
        *designer_round(2),
        *verifier_round(2),
    ]
    result, _, events = await run_loop(script)
    assert "stop: repeated_failure" in result.answer
    assert len(tasks_of(events, "designer")) == 2


async def test_a_design_run_replays_offline_from_its_log(verdicts):
    """The rule steps and the nested runs give the same calls again, with no model."""
    verdicts.append(PASSED)
    script = [*designer_round(1), *verifier_round(1), says("costs"), says("explained")]
    result, engine, _ = await run_loop(script)
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.status, replayed.answer) == (result.status, result.answer)


async def test_a_run_without_a_case_asks_the_user_before_designing(verdicts):
    """No agent runs before the question; the answer goes to the designer, which sets the case."""
    verdicts.append(PASSED)
    case, files = example_case("shallow_district")
    economics = json.loads(files["economics.json"])
    named = {
        item["name"]: {k: v for k, v in item.items() if k != "name"}
        for item in case["requirements"]
    }
    changes = {
        key: value for key, value in case.items() if key not in ("requirements", "economics")
    }
    script = [
        uses(call("set_case", "c1", changes=changes, requirements=named, economics=economics)),
        *designer_round(1),
        *verifier_round(1),
        says("costs"),
        says("explained"),
    ]
    result, engine, events = await run_loop(script, case=None)
    for name, content in files.items():
        engine.store.save_chat_artifact(result.run_id, f"case/{name}", content)
    assert result.status == "waiting"
    assert "no case" in result.request.message
    assert agents_of(events) == []
    resumed = await DesignLoop(Designer(), Verifier()).resume(
        engine, result.run_id, result.request.id, {"text": "the project's heating"}
    )
    events = engine.store.load_events(result.run_id)
    first = tasks_of(events, "designer")[0]
    assert "The user answered the question on the case: the project's heating" in first
    assert resumed.status == "done" and "stop: verified" in resumed.answer
    problem = recover(events).problem
    assert problem.case == problem.case_origin["case"] == case


async def test_a_case_without_demand_asks_the_user():
    """A case that demands nothing is not designed for."""
    result, _, events = await run_loop([], case=NO_DEMAND)
    assert result.status == "waiting"
    assert "no demand" in result.request.message
    assert agents_of(events) == []


async def test_a_designer_that_leaves_no_case_stops_with_no_case_at_the_limit():
    """At the last round the driver stops with a clear answer instead of asking again."""
    result, engine, _ = await run_loop([says("no case"), says("still none")], case=None)
    resumed = await DesignLoop(Designer(), Verifier(), max_rounds=1).resume(
        engine, result.run_id, result.request.id, {"text": "nothing"}
    )
    assert resumed.status == "done"
    assert "stop: no_case" in resumed.answer and "no case" in resumed.answer


def test_the_request_is_the_run_s_own_message_after_the_chat_s_history():
    """An earlier turn of the chat is history: the designer and the explainer get the new one."""
    messages = [
        Message(role="user", content="OLD: what is LCOH?"),
        Message(role="assistant", content="The levelised cost of heat."),
        Message(role="user", content="NEW: design a plant"),
    ]
    assert request_of(Context(messages=messages)) == "NEW: design a plant"


async def test_the_designer_s_first_task_is_the_newest_message(verdicts):
    """With an earlier turn in the context, round 1 starts from the run's own message."""
    verdicts.append(PASSED)
    script = [*designer_round(1), *verifier_round(1), says("costs"), says("explained")]
    engine = engine_for(script)
    start = context("NEW: design a plant", problem=ProblemState(case=CASE))
    start.messages[:0] = [
        Message(role="user", content="OLD: what is LCOH?"),
        Message(role="assistant", content="The levelised cost of heat."),
    ]
    result = await DesignLoop(Designer(), Verifier()).run(engine, start)
    events = engine.store.load_events(start.run_id)
    assert result.status == "done"
    assert tasks_of(events, "designer")[0].startswith("NEW: design a plant")
    assert "OLD" not in tasks_of(events, "explainer")[0]


CHANGED = {
    "passed": False,
    "checks": [],
    "failures": [
        {
            "name": "case_changed",
            "domain": "coupled",
            "detail": "the case differs",
            "changes": [{"path": "constraints", "change": "removed", "given": {"on": "d0"}}],
        }
    ],
}
ORIGIN = {"case": CASE, "files": {}}


async def test_a_changed_case_asks_the_user_and_an_approval_goes_on_to_the_costs(verdicts):
    """The driver asks with two options; on approve it accepts the case and checks again."""
    verdicts.extend([CHANGED, PASSED])
    script = [*designer_round(1), *verifier_round(1), says("costs"), says("explained")]
    result, engine, events = await run_loop(script, origin=ORIGIN)
    assert result.status == "waiting"
    assert "changed the case you gave" in result.request.message
    assert "constraints: removed" in result.request.message
    assert [option.value for option in result.request.options] == ["approve", "restore"]
    resumed = await DesignLoop(Designer(), Verifier()).resume(
        engine, result.run_id, result.request.id, {"text": "approve"}
    )
    events = engine.store.load_events(result.run_id)
    assert resumed.status == "done" and "stop: verified" in resumed.answer
    assert agents_of(events) == ["designer", "verifier", "economist", "explainer"]
    assert recover(events).problem.case_origin["case"] == CASE


async def test_a_refused_change_sends_the_designer_back_to_the_user_s_case(verdicts):
    """On restore the next round is told to set the case back with source='origin'."""
    verdicts.extend([CHANGED, PASSED])
    script = [*designer_round(1), *verifier_round(1), *designer_round(2), *verifier_round(2)]
    script += [says("costs"), says("explained")]
    result, engine, _ = await run_loop(script, origin=ORIGIN)
    resumed = await DesignLoop(Designer(), Verifier()).resume(
        engine, result.run_id, result.request.id, {"text": "restore"}
    )
    events = engine.store.load_events(result.run_id)
    second = tasks_of(events, "designer")[1]
    assert resumed.status == "done"
    assert "set_case(source='origin')" in second and second.startswith("Design the plant")


async def test_the_explainer_reads_the_verifier_s_report(verdicts):
    """The verifier's answer, with its notes on the case and the assumptions, reaches the user."""
    verdicts.append(PASSED)
    script = [*designer_round(1), *verifier_round(1), says("costs"), says("explained")]
    _, _, events = await run_loop(script)
    assert "The verifier's report:\n\nchecked" in tasks_of(events, "explainer")[0]


def test_the_economist_compares_only_what_the_designer_ran():
    """The sized start and the simulated alternatives are named; none means nothing to compare."""
    design = {
        "reference": "design/best",
        "start_result": "result/start",
        "alternatives": [{"family": "F2", "design": "design/f2", "result": "result/f2"}],
    }
    task = economist_task("design/best", "result/best", ProblemState(design=design))
    assert "compare it with result/start, result/f2" in task
    empty = economist_task("design/best", "result/best", ProblemState())
    assert "no sized start or alternative" in empty


def plant_context(plants):
    """Return a context of project ``p1`` whose workspace holds the plant files ``plants``."""
    session = StubSession(workspace=MemoryWorkspace(plants={"p1": plants}))
    return Context(
        messages=[Message(role="user", content="Size the plant")], project="p1", session=session
    )


def test_the_first_task_names_the_project_s_plants():
    """The designer needs no discovery step: the task lists the plant files, sorted."""
    task = DesignDriver().first_task(plant_context({"Zeta": {}, "Alpha": {}}))
    assert "The project's plants: Alpha, Zeta." in task
    assert "project_plant" in task and task.startswith("Size the plant")


def test_the_first_task_says_nothing_of_plants_when_the_project_has_none():
    """Without plant files, or without a project, the task is the request and the rounds."""
    without_files = DesignDriver().first_task(plant_context({}))
    without_project = DesignDriver().first_task(context("Size the plant", session=StubSession()))
    assert "plants" not in without_files and without_files == without_project


def test_the_recorded_designer_stores_the_project_plant_before_its_first_study():
    """In the recording, the first study call reads a design built from the project's plant."""
    path = Path("evals/recordings/designer/project_plant.jsonl")
    calls = [
        call for line in path.read_text().splitlines() for call in json.loads(line)["tool_calls"]
    ]
    names = [item["name"] for item in calls]
    read = calls[names.index("read_plant")]["input"]
    built = calls[names.index("build_plant")]["input"]
    study = calls[names.index("size_plant")]["input"]
    project_file = Path("evals/projects/hackathon/plants") / f"{read['project_plant']}.json"
    assert names.index("list_plants") < names.index("read_plant") < names.index("build_plant")
    assert names.index("build_plant") < names.index("size_plant")
    assert built["plant"]["type"] == json.loads(project_file.read_text())["type"]
    assert study["design"] == f"design/{built['name']}"


OLD_DESIGN = {
    "reference": "design/best",
    "result": "result/r2",
    "start_result": {"reference": "result/r0", "summary": "start"},
    "alternatives": [{"family": "F2", "design": "design/f2", "result": {"reference": "result/r3"}}],
}


def test_a_0_4_state_with_objects_for_references_loads_and_the_economist_task_reads_it():
    """An object that carries a reference is converted; the economist task does not crash."""
    problem = ProblemState.model_validate({"design": OLD_DESIGN})
    task = economist_task("design/best", "result/r2", problem)
    assert problem.design["start_result"] == "result/r0"
    assert "result/r0, result/r3" in task


def test_an_object_without_a_reference_is_set_aside_and_named_not_crashed_on():
    """What cannot be converted moves to ``design.unreadable`` and the task goes on."""
    problem = ProblemState.model_validate({"design": {"start_result": {"summary": "x"}}})
    assert problem.design["unreadable"] == {"start_result": {"summary": "x"}}
    assert "no sized start" in economist_task("design/a", "result/b", problem)


def test_update_state_refuses_an_object_where_a_reference_belongs_and_shows_the_shape():
    """The state change is refused with the field path and the expected string."""
    from geomind.context.state import apply_changes
    from geomind.errors import StateError

    change = [{"op": "add", "path": "/design/start_result", "value": {"reference": "result/r"}}]
    with pytest.raises(StateError, match="design.*start_result.*string"):
        apply_changes(ProblemState(), change)


def test_the_recorded_designer_asks_for_a_missing_range_and_never_sets_one():
    """In the recording, a plant without a range ends in ask_user after the question is recorded."""
    path = Path("evals/recordings/designer/missing_range.jsonl")
    calls = [
        call for line in path.read_text().splitlines() for call in json.loads(line)["tool_calls"]
    ]
    names = [item["name"] for item in calls]
    assert "set_ranges" not in names
    assert names.index("update_state") < names.index("ask_user")
    recorded = calls[names.index("update_state")]["input"]["changes"][0]
    assert recorded["path"] == "/questions/-"


def test_the_designer_prompt_asks_instead_of_inventing_a_range():
    """The prompt and the skill say ranges come from the user or the case, and to ask."""
    root = Path("geomind/prompts")
    for text in (
        (root / "design" / "designer.md").read_text(),
        (root / "skills" / "designing-a-plant.md").read_text(),
    ):
        assert "ask_user" in text and ("invent" in text or "Never fill a missing one" in text)
