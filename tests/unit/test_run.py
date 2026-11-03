"""The facade: exactly the contract's use."""

import asyncio
import json

import pytest

import geomind as gd
from geomind import runtime
from geomind.agents import AnalysisLead, Route
from geomind.engine.recovery import recover
from geomind.errors import ProviderError, RequestError, RunError
from geomind.loops import DesignLoop
from geomind.providers import FakeLLM
from geomind.run import LOOPS, loop_of
from geomind.stores import MemoryRunStore
from tests.fixtures.runs import ROUTE, Worker, call, of_type, routed, says, uses


@pytest.fixture(autouse=True)
def no_retry_delay():
    """Retry without sleeping."""
    with runtime.settings(retry_delay=0):
        yield


def run_of(script, **options):
    """Return a run with a scripted provider; without an agent the coordinator routes it first."""
    routing = [] if "agent" in options else [ROUTE]
    return gd.Run(message="hello", llm=FakeLLM([*routing, *script]), **options)


def test_start_answers():
    """The simplest use."""
    result = run_of([says("hi")]).start()
    assert (result.status, result.answer) == ("done", "hi")


async def test_astart_for_async_callers():
    """The same run inside an event loop."""
    assert (await run_of([says("hi")]).astart()).answer == "hi"


async def test_sync_form_inside_an_event_loop_raises():
    """The error says what to use."""
    with pytest.raises(RunError, match="astart"):
        run_of([says("hi")]).start()


def test_history_comes_before_the_message():
    """A chat continues."""
    llm = FakeLLM([says()])
    history = [gd.Message(role="user", content="before")]
    gd.Run(message="now", history=history, llm=llm).start()
    contents = [message.content for message in llm.calls[0]["messages"]]
    assert contents.index("before") < contents.index("now")


def test_run_started_reports_the_tool_loop():
    """The contract's event, with the chat in the log."""
    store = gd.stores.MemoryRunStore()
    run = run_of([says()], store=store, chat="c1", project="p1")
    run.start()
    event = of_type(store.load_events(run.id), "run.started")[-1]
    assert event.data() == {"run": run.id, "loop": "tool", "agent": "analysis_lead", "parent": None}
    assert (event.chat, event.project) == ("c1", "p1")


def test_default_llm_is_openrouter(monkeypatch):
    """Without a provider the run uses OpenRouter, and so needs a key."""
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    with pytest.raises(ProviderError, match="OPENROUTER_API_KEY"):
        gd.Run(message="x")


def test_an_unrouted_run_starts_with_the_analysis_lead():
    """Before the coordinator routes it, a run's tool loop holds the analysis lead."""
    assert type(run_of([]).loop.agent) is AnalysisLead


def question_script():
    """Return a run that asks one question."""
    return [uses(call("ask_user", question="which?")), says("end")]


def test_load_and_resume_in_a_fresh_run(tmp_path):
    """Nothing survives but the files."""
    run = run_of(question_script(), store=gd.stores.FileRunStore(tmp_path))
    paused = run.start()
    assert paused.status == "waiting"

    fresh = gd.Run.load(
        run.id, llm=FakeLLM(question_script()[1:]), store=gd.stores.FileRunStore(tmp_path)
    )
    assert fresh.resume(paused.request.id, {"text": "this"}).answer == "end"


def test_resume_on_the_same_object():
    """The caller need not reload."""
    run = run_of(question_script())
    paused = run.start()
    assert run.resume(paused.request.id, {"text": "x"}).answer == "end"


async def test_aresume_for_async_callers():
    """The same resume inside an event loop."""
    run = run_of(question_script())
    paused = await run.astart()
    assert (await run.aresume(paused.request.id, {"text": "x"})).answer == "end"


def test_load_of_an_unknown_run_raises(tmp_path):
    """Nothing is stored."""
    with pytest.raises(RunError, match="expected a log"):
        gd.Run.load("nope", llm=FakeLLM([]), store=gd.stores.FileRunStore(tmp_path))


def test_resume_of_a_dead_run_continues_from_its_events():
    """A run with a logged completion continues without a second LLM call."""

    class Dying(gd.stores.MemoryRunStore):
        kind = "tool.started"

        def save_event(self, run_id, event):
            if event.type == self.kind:
                self.kind = None
                raise SystemExit
            super().save_event(run_id, event)

    store = Dying()
    permissions = gd.Permissions(mode="auto")
    run = run_of([uses(call("ask_user", question="q"))], store=store, permissions=permissions)
    with pytest.raises(SystemExit):
        run.start()
    fresh = gd.Run.load(run.id, llm=FakeLLM([]), store=store, permissions=permissions)
    paused = fresh.resume()
    assert paused.status == "waiting"


def test_load_takes_the_contract_keywords():
    """Permissions are passed again, as hooks and callbacks are."""
    permissions = gd.Permissions(mode="readonly")
    run = run_of(question_script())
    run.start()
    fresh = gd.Run.load(run.id, llm=FakeLLM([]), store=run.store, permissions=permissions)
    assert fresh.engine.permissions is permissions


def test_run_and_load_take_no_sandbox():
    """The code sandbox is gone: no code runs in geomind, so neither takes ``sandbox``."""
    with pytest.raises(TypeError):
        gd.Run(message="x", llm=FakeLLM([]), sandbox=object())


def test_cancel_stops_at_the_next_hook_point():
    """Cancelling from a callback ends the run."""
    run = run_of([uses(call("ask_user", question="q"))])

    class Canceller(gd.callbacks.Callback):
        def on_llm_call(self, engine, event):
            run.cancel()

    run.engine.callbacks.append(Canceller())
    result = run.start()
    assert (result.status, result.stop_reason) == ("cancelled", "cancelled")


def test_answering_twice_raises():
    """A second answer finds nothing to answer."""
    script = [uses(call("ask_user", question="a")), uses(call("ask_user", "c2", question="b"))]
    run = run_of(script)
    first = run.start()
    run.resume(first.request.id, {"text": "x"})
    with pytest.raises(RequestError):
        run.resume(first.request.id, {"text": "x"})


def test_an_agent_replaces_the_routing():
    """One agent can be tried by hand, and it is the one a loaded run rebuilds."""
    store = MemoryRunStore()
    run = run_of([says()], agent=Worker(), store=store)
    result = run.start()
    assert type(gd.Run.load(result.run_id, llm=FakeLLM([]), store=store).loop.agent) is Worker


def test_a_loaded_design_run_keeps_its_round_limit():
    """``Run.load`` rebuilds the design loop with the ``max_rounds`` it started with."""
    from geomind.agents import DesignLead, Reviewer
    from geomind.run import loop_for

    store = MemoryRunStore()
    run = run_of([], store=store)
    run.loop = DesignLoop(DesignLead(), Reviewer(), max_rounds=2)
    run.start()
    state = recover(store.load_events(run.id), run.id)
    assert loop_for(state).max_rounds == 2


def test_run_load_rebuilds_the_compare_loop():
    """A stored compare run comes back as a compare loop, not as a design loop."""
    from geomind.agents import DesignLead, Reviewer
    from geomind.loops import CompareLoop
    from geomind.run import loop_for

    store = MemoryRunStore()
    run = run_of([], store=store)
    run.loop = CompareLoop(DesignLead(), Reviewer(), max_rounds=3)
    run.start()
    loaded = loop_for(recover(store.load_events(run.id), run.id))
    assert (type(loaded), loaded.max_rounds) == (CompareLoop, 3)


def test_a_route_to_the_tool_loop_runs_its_agent():
    """The table names the agent."""
    loop = loop_of(Route(kind="loop", agent="analysis_lead"))
    assert isinstance(loop.agent, AnalysisLead)


def test_the_tables_hold_only_loops_that_are_built():
    """A route can name no unbuilt loop, so a live request never ends in ``not_implemented``."""
    assert set(LOOPS) == {"tool", "project", "design", "compare"}
    assert set(Route.model_fields["loop"].annotation.__args__) == set(LOOPS)
    assert "brief" not in Route.model_fields


def test_a_run_without_an_agent_is_routed_by_the_coordinator():
    """The backend names no loop and no agent: the coordinator's route picks them, in the log."""
    store = MemoryRunStore()
    result = gd.Run(message="hello", llm=FakeLLM([ROUTE, says("the answer")]), store=store).start()
    events = store.load_events(result.run_id)
    started = of_type(events, "run.started")
    assert (result.status, result.answer) == ("done", "the answer")
    assert [(event.agent, event.parent) for event in started] == [
        ("coordinator", result.run_id),
        ("analysis_lead", None),
    ]
    sequences = [event.sequence for event in events]
    assert sequences == sorted(set(sequences))
    assert recover(events).run_id == result.run_id


def test_a_design_request_starts_the_design_loop():
    """A design request needs no loop name from the backend."""
    run = gd.Run(message="design", llm=FakeLLM([routed("design")]))
    asyncio.run(run._route_message())
    assert isinstance(run.loop, DesignLoop)


def test_a_project_request_starts_the_project_lead():
    """The coordinator's ``project`` route runs the project lead in the project loop."""
    from geomind.agents import ProjectLead
    from geomind.loops import ProjectLoop

    run = gd.Run(message="design", llm=FakeLLM([routed("project")]))
    asyncio.run(run._route_message())
    assert isinstance(run.loop, ProjectLoop) and isinstance(run.loop.agent, ProjectLead)


def test_the_brief_follows_the_message_and_preferences_join_the_state():
    """An app event gets the coordinator's brief; the user's preferences reach every agent."""
    from geomind.context import render

    route = routed(
        "project",
        task="The user saved the case form; check the design.",
        preferences={"display_units": "degC"},
    )
    store = MemoryRunStore()
    run = gd.Run(message="saved", llm=FakeLLM([route, says("ok")]), store=store, chat="c")
    result = run.start()
    started = of_type(store.load_events(result.run_id), "run.started")[-1]
    assert [message.content for message in started.messages][-2:] == [
        "saved",
        "The coordinator's brief: The user saved the case form; check the design.",
    ]
    assert started.problem["preferences"] == {"display_units": "degC"}
    shown = render(gd.context.ProblemState.model_validate(started.problem))
    assert 'User preferences: {"display_units": "degC"}' in shown


def test_a_short_answer_route_ends_the_run_with_it():
    """A greeting is answered by the route itself, by rule."""
    answer = says(json.dumps({"kind": "answer", "answer": "Hello."}))
    result = gd.Run(message="hi", llm=FakeLLM([answer])).start()
    assert (result.status, result.answer) == ("done", "Hello.")


def test_a_loop_set_by_hand_is_not_routed():
    """``--loop`` and tests choose the loop; the coordinator is not asked."""
    run = gd.Run(message="hello", llm=FakeLLM([says("hi")]))
    run.loop = loop_of(Route(kind="loop", loop="tool", agent="analysis_lead"))
    assert run.start().answer == "hi"
