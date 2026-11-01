"""``DesignLoop``: propose, simulate, verify, route the failures by domain, and repeat."""

import pytest

from geomind.agents import Designer, Verifier
from geomind.context import ProblemState
from geomind.engine import Context, Engine
from geomind.engine.hooks import Verified
from geomind.engine.recovery import recover
from geomind.loops import DesignLoop
from geomind.loops.design import DesignDriver, repeated, request_of, routed_task
from geomind.types import Message
from tests.fixtures.runs import call, context, engine_for, logged, of_type, same_usage, says, uses

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


async def run_loop(completions, case=CASE, max_rounds=5):
    """Run a design loop on scripted completions; return the result and the events."""
    engine = engine_for(completions)
    start = context("Design the plant of the case.", problem=ProblemState(case=case))
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
    case = {"op": "add", "path": "/case", "value": CASE}
    script = [
        uses(call("update_state", "c1", changes=[case])),
        *designer_round(1),
        *verifier_round(1),
        says("costs"),
        says("explained"),
    ]
    result, engine, events = await run_loop(script, case=None)
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
