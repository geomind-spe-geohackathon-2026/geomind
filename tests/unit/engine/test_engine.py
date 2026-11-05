"""The engine: stop reasons and limits."""

from geomind.engine import Engine, Permissions
from geomind.engine.hooks import TokenBudget
from geomind.errors import ProviderError
from geomind.providers import FakeLLM
from geomind.types import Usage
from tests.fixtures.runs import (
    Worker,
    call,
    context,
    of_type,
    run,
    says,
    stopped_at_limit,
    types,
    uses,
)


async def test_step_started_names_the_model_of_the_call():
    """The contract's ``model`` is what the step calls."""
    _, _, events = await run([says("hello")])
    assert of_type(events, "step.started")[0].data()["model"] == "fake/model"


async def test_answer_stops_a_run():
    """No tool calls means the text is the answer."""
    result, _, events = await run([says("hello")])
    assert (result.status, result.stop_reason, result.answer) == ("done", "answer", "hello")
    assert result.steps == 1 and result.usage.input_tokens == 10
    assert types(events)[-1] == "run.finished"


async def test_step_limit_stops_a_run():
    """A run is finite."""
    calls = [uses(call("lookup", f"c{index}", key="k")) for index in range(5)]
    result, engine, _ = await run(calls, max_steps=2, permissions=Permissions(mode="ask"))
    result = await stopped_at_limit(engine, result)
    events = engine.store.load_events(result.run_id)
    assert (result.status, result.stop_reason, result.steps) == ("failed", "step_limit", 2)
    assert of_type(events, "run.finished")[0].message == "stopped after 2 steps"


async def test_provider_failure_ends_the_run_with_an_error():
    """After the retries the run fails and says why."""
    result, _, events = await run([ProviderError("bad key")])
    assert (result.status, result.stop_reason) == ("failed", "error")
    assert of_type(events, "error")[0].where == "engine"
    assert of_type(events, "run.finished")[0].message == "bad key"


async def test_steps_left_reaches_the_model():
    """The dynamic part counts down."""
    _, engine, _ = await run([uses(call("lookup", key="k")), says()], max_steps=5)
    last = [call_["messages"][-1].content for call_ in engine.llm.llm.calls]
    assert last == ["Steps left: 4", "Steps left: 3"]


async def test_hook_handles_can_be_removed():
    """A removed hook no longer decides."""
    engine = Engine(llm=FakeLLM([says("ok")]))
    handle = engine.register_hook(TokenBudget(0))
    handle.remove()
    assert (await engine.run(Worker(), context())).answer == "ok"


async def test_default_permissions_ask():
    """A new engine asks before anything that changes something."""
    assert Engine().permissions.mode == "ask"
    assert isinstance(Engine().permissions, Permissions)


async def test_usage_event_holds_running_totals():
    """The totals grow step by step."""
    _, _, events = await run([uses(call("lookup", key="k")), says()])
    totals = [event.input_tokens for event in of_type(events, "usage")]
    assert totals == [10, 20]
    step = of_type(events, "step.finished")[1].usage
    assert step == Usage(input_tokens=10, output_tokens=5, cost=0.01)


def test_a_crash_is_its_class_message_and_place():
    """QA-319: a nested crash said only "'str' object has no attribute 'get'", no class or line."""
    from geomind.engine.engine import crash_text

    try:
        "text".get("x")
    except AttributeError as error:
        text = crash_text(error)
    assert text.startswith("AttributeError: 'str' object has no attribute 'get' at ")
    assert "test_engine.py:" in text


async def test_auto_approve_answers_a_question_with_its_proposal_and_lists_it():
    """QA-339: with Auto-approve on nobody is asked; the proposal is taken, kept and listed."""
    from geomind.engine import Permissions
    from geomind.engine.engine import AUTO_HEADING
    from geomind.engine.recovery import recover
    from tests.fixtures.runs import Worker, call, context, engine_for, of_type, says, uses

    question = call(
        "ask_user", "q", question="Approve the case values?", options=["approve all", "stop"]
    )
    script = [uses(question), says("done")]
    engine = engine_for(script, permissions=Permissions(mode="auto"))
    start = context()
    result = await engine.run(Worker(), start, max_steps=5)
    assert result.status == "done" and result.request is None
    assert result.answer.startswith("done") and AUTO_HEADING in result.answer
    events = engine.store.load_events(start.run_id)
    [auto] = of_type(events, "question.auto_answered")
    assert (auto.tool, auto.answer) == ("ask_user", "approve all")
    assert [e.rule for e in of_type(events, "permission") if e.call_id == "q"][-1] == "auto"
    assumptions = recover(events, start.run_id).problem.assumptions
    [kept] = [item for item in assumptions if item.source == "auto-approve"]
    assert kept.id == "AUTO-1" and kept.value == "approve all"
    assert "ask_user: Approve the case values? -> approve all" in result.answer


async def test_without_auto_approve_the_question_waits_for_the_user():
    """Ask mode: the same question pauses the run, as before."""
    from geomind.engine import Permissions
    from tests.fixtures.runs import Worker, call, context, engine_for, says, uses

    question = call("ask_user", "q", question="Which?", options=["a", "b"])
    engine = engine_for([uses(question), says("done")], permissions=Permissions(mode="ask"))
    result = await engine.run(Worker(), context(), max_steps=5)
    assert result.status == "waiting" and result.request.kind == "question"


def test_the_proposal_is_the_tool_s_then_the_first_option_then_go_on():
    """``proposed`` wins, else the first option, else the note to go on with one's own proposal."""
    from geomind.engine.engine import AUTO_TEXT, proposed_answer
    from geomind.types import Request

    asked = Request(kind="question", message="m", options=["approve all", "stop"])
    assert proposed_answer(asked) == "approve all"
    assert proposed_answer(asked.model_copy(update={"proposed": "stop"})) == "stop"
    assert proposed_answer(Request(kind="question", message="free")) == AUTO_TEXT


async def test_a_run_auto_approve_answered_replays():
    """The auto answer, its assumption and the listed block come back the same in a replay."""
    from geomind.engine import Engine, Permissions
    from tests.fixtures.runs import Worker, call, context, engine_for, says, uses

    question = call("ask_user", "q", question="Approve?", options=["approve all", "stop"])
    engine = engine_for([uses(question), says("done")], permissions=Permissions(mode="auto"))
    start = context()
    result = await engine.run(Worker(), start, max_steps=5)
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.status, replayed.answer) == (result.status, result.answer)


async def test_a_question_asked_before_a_restart_is_answered_by_a_resume_in_auto_mode():
    """QA-354: the run waited 11 min on a question asked across a restart; resume answers it."""
    from geomind.engine import Permissions
    from tests.fixtures.runs import Worker, call, context, engine_for, says, uses

    question = call("ask_user", "q", question="Approve?", options=["approve all", "stop"])
    first = engine_for([uses(question)], permissions=Permissions(mode="ask"))
    start = context()
    waiting = await first.run(Worker(), start, max_steps=5)
    assert waiting.status == "waiting"
    later = engine_for([says("done")], permissions=Permissions(mode="auto"))
    later.store = first.store
    result = await later.resume(waiting.run_id, agent=Worker())
    assert result.status == "done" and "approve all" in result.answer
