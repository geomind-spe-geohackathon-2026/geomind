"""``DesignLoop``: propose, simulate, verify, route the failures by domain, and repeat."""

import asyncio

import pytest

import geomind as gd
from geomind.agents import Designer, Verifier
from geomind.engine import Engine
from geomind.engine.hooks import Verified
from geomind.engine.recovery import recover
from geomind.loops import DesignLoop
from geomind.loops.design import DesignDriver, repeated, routed_brief
from geomind.types import ToolCall
from tests.fixtures.calls import call as call_tool
from tests.fixtures.hackathon import base_spec, hackathon_spec
from tests.fixtures.runs import call, context, engine_for, logged, of_type, same_usage, says, uses
from tests.fixtures.sessions import StubSession

TOOLS = gd.tools.gemini
WINTER = {"start": "2027-01-01", "end": "2027-01-03"}
SPRING = {"start": "2027-03-29", "end": "2027-03-31"}
FAILED = {
    "passed": False,
    "checks": [
        {
            "name": "heat_users.supply_in.temperature",
            "passed": False,
            "value": {"value": 339.45, "unit": "K"},
            "limit": {"value": [373.149, 373.151], "unit": "K"},
        },
        {
            "name": "d0.flow",
            "passed": False,
            "value": {"value": 0.1, "unit": "m3/s"},
            "limit": {"value": [0.0139, 0.0833], "unit": "m3/s"},
        },
        {
            "name": "heat_users.unmet_demand",
            "passed": False,
            "value": {"value": 2e6, "unit": "W"},
            "limit": {"value": 0.001, "unit": "W"},
        },
        {
            "name": "plant energy",
            "passed": False,
            "value": {"value": 0.1, "unit": "-"},
            "limit": {"value": 1e-6, "unit": "-"},
        },
    ],
    "failures": [
        {"name": "heat_users.supply_in.temperature", "domain": "surface"},
        {"name": "d0.flow", "domain": "subsurface"},
        {"name": "heat_users.unmet_demand", "domain": "sizing"},
        {"name": "plant energy", "domain": "coupled"},
    ],
}


@pytest.fixture(scope="module")
def references():
    """Return the result references of the base design in winter and the example in spring."""
    import gemini as gm

    session = StubSession()

    async def store():
        found = {}
        for name, spec, window in (
            ("base", base_spec(gm), WINTER),
            ("hackathon", hackathon_spec(gm), SPRING),
        ):
            await call_tool(TOOLS.build_plant, {"plant": spec, "name": name}, session)
            ran = await call_tool(TOOLS.simulate, {"design": f"design/{name}", **window}, session)
            found[name] = ran.output["reference"]
        return found

    return {
        **asyncio.run(store()),
        "specs": {"base": base_spec(gm), "hackathon": hackathon_spec(gm)},
    }


def built(references, name, window, index):
    """Return the designer's completions: build, simulate, record the design, hand over."""
    design = f"design/{name}"
    record = {"op": "replace", "path": "/design", "value": {"reference": design}}
    return [
        uses(
            ToolCall(
                id=f"b{index}",
                name="build_plant",
                input={"plant": references["specs"][name], "name": name},
            ),
            call("simulate", f"s{index}", design=design, **window),
            call("update_state", f"u{index}", changes=[record]),
        ),
        says(design),
    ]


def designer_round(references, name, window, index):
    """Return the designer's completions: set the brief, then build, simulate and record."""
    brief = uses(call("set_brief", f"p{index}", preset="hackathon_2027"))
    return [brief, *built(references, name, window, index)]


def verifier_round(references, name, window, index):
    """Return the verifier's completions: simulate afresh, check, record the result, report."""
    result = references[name]
    record = {"op": "replace", "path": "/verification", "value": {"result": result}}
    return [
        uses(call("simulate", f"vs{index}", design=f"design/{name}", **window)),
        uses(call("check_results", f"vc{index}", reference=result)),
        uses(call("update_state", f"vu{index}", changes=[record])),
        says("checked"),
    ]


async def run_loop(completions, max_rounds=5):
    """Run a design loop on scripted completions; return the result and the events."""
    engine = engine_for(completions)
    start = context("Design the plant of the brief.")
    result = await DesignLoop(Designer(), Verifier(), max_rounds=max_rounds).run(engine, start)
    return result, engine, engine.store.load_events(start.run_id)


def tasks_of(events, agent):
    """Return the tasks the loop gave one agent, in order."""
    return [e.messages[0].content for e in of_type(events, "run.started") if e.agent == agent]


def test_the_constructor_is_final():
    """Two agents and a limit; the run starts with a driver whose first move is the designer."""
    first = Designer()
    loop = DesignLoop(designer=first, verifier=Verifier())
    assert (loop.name, loop.max_rounds) == ("design", 5)
    assert isinstance(loop.agent, DesignDriver)
    assert loop.agent.tools()["designer"].agent is first


def test_a_brief_routes_each_failure_to_its_side():
    """Subsurface, surface, resizing and coupled failures each get their own instruction."""
    brief = routed_brief(2, 5, "design/a", "result/r", FAILED)
    assert brief.index("Subsurface side") < brief.index("d0.flow")
    assert brief.index("Surface side") < brief.index("heat_users.supply_in.temperature")
    assert brief.index("Resize") < brief.index("heat_users.unmet_demand")
    assert "subsurface first, then the surface" in brief
    assert "339.45 K" in brief and "stale" in brief


def test_the_same_failures_twice_are_repeated():
    """The loop stops when one round fails exactly as the one before."""
    assert repeated([["a", "b"], ["b", "a"]])
    assert not repeated([["a"], ["a", "b"]])
    assert not repeated([["a"]])


@pytest.mark.slow
async def test_a_design_that_passes_is_costed_explained_and_answered(references):
    """Round 1 passes: the economist and the explainer follow, and the explanation is the answer.

    NOTE: slow, because the loop and the ``Verified`` hook each run gemini's checks again.
    """
    script = [
        *designer_round(references, "base", WINTER, 1),
        *verifier_round(references, "base", WINTER, 1),
        says("capex 41 MEUR"),
        says("## Design\nTwo doublets."),
    ]
    result, engine, events = await run_loop(script)
    assert (result.status, result.stop_reason) == ("done", "finish")
    assert "## Design\nTwo doublets." in result.answer
    assert [e.agent for e in of_type(events, "run.started")][1:] == [
        "designer",
        "verifier",
        "economist",
        "explainer",
    ]
    assert any(isinstance(hook, Verified) for hook in engine.hooks())
    assert "stop: verified" in of_type(events, "run.finished")[-1].answer
    assert same_usage(result.usage, logged(events)) and result.usage.input_tokens > 0


@pytest.mark.slow
async def test_a_failed_round_sends_its_failures_to_the_designer(references):
    """The example fails its supply temperature; round 2 is told so, on the surface side.

    NOTE: slow, because each round runs gemini's checks.
    """
    script = [
        *designer_round(references, "hackathon", SPRING, 1),
        *verifier_round(references, "hackathon", SPRING, 1),
        *designer_round(references, "base", WINTER, 2),
        *verifier_round(references, "base", WINTER, 2),
        says("costs"),
        says("explained"),
    ]
    result, _, events = await run_loop(script)
    second = tasks_of(events, "designer")[1]
    assert result.status == "done"
    assert "Round 2 of at most 5" in second
    assert second.index("Surface side") < second.index("heat_users.supply_in.temperature")


@pytest.mark.slow
async def test_the_round_limit_stops_without_presenting_a_design(references):
    """A design that never passes is moved to ``design.rejected``, and the answer says why.

    NOTE: slow, because each round runs gemini's checks.
    """
    script = [
        *designer_round(references, "hackathon", SPRING, 1),
        *verifier_round(references, "hackathon", SPRING, 1),
    ]
    result, _, events = await run_loop(script, max_rounds=1)
    problem = recover(events).problem
    assert result.status == "done"
    assert "stop: max_rounds" in result.answer
    assert "reference" not in problem.design
    assert problem.design["rejected"] == ["design/hackathon"]


@pytest.mark.slow
async def test_the_same_failures_twice_stop_the_loop(references):
    """Two rounds that fail alike end the loop before the round limit.

    NOTE: slow, because each round runs gemini's checks.
    """
    script = [
        *designer_round(references, "hackathon", SPRING, 1),
        *verifier_round(references, "hackathon", SPRING, 1),
        *designer_round(references, "hackathon", SPRING, 2),
        *verifier_round(references, "hackathon", SPRING, 2),
    ]
    result, _, events = await run_loop(script)
    assert "stop: repeated_failure" in result.answer
    assert len(tasks_of(events, "designer")) == 2


@pytest.mark.slow
async def test_a_design_run_replays_offline_from_its_log(references):
    """The rule steps and the nested runs give the same calls again, with no model.

    NOTE: slow, because the replay runs gemini's tools and checks again.
    """
    script = [
        *designer_round(references, "base", WINTER, 1),
        *verifier_round(references, "base", WINTER, 1),
        says("costs"),
        says("explained"),
    ]
    result, engine, _ = await run_loop(script)
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.status, replayed.answer) == (result.status, result.answer)


async def test_a_design_run_without_a_demand_asks_the_user():
    """A brief without demand is not designed for: the driver asks the user, and passes it on."""
    no_demand = {"doublets": {"min": 1, "max": 3}}
    script = [
        uses(call("set_brief", "p1", changes=no_demand)),
        says("no demand given"),
        says("still none"),
    ]
    result, engine, _ = await run_loop(script, max_rounds=2)
    assert result.status == "waiting"
    assert "no demand" in result.request.message and "demand" in result.request.message
    resumed = await DesignLoop(Designer(), Verifier(), max_rounds=2).resume(
        engine, result.run_id, result.request.id, {"text": "the hackathon profiles"}
    )
    second = tasks_of(engine.store.load_events(result.run_id), "designer")[1]
    assert "The user answered the question on the brief: the hackathon profiles" in second
    assert "stop: no_brief after round 2" in resumed.answer
