"""A nested run: its id, its events, its pause and its place in the log."""

import pytest

import geomind as gd
from geomind import runtime
from geomind.engine import Engine, Permissions
from geomind.engine.recovery import recover
from geomind.providers import FakeLLM
from geomind.stores.run import MemoryRunStore
from tests.fixtures.runs import EXECUTED, Lead, call, context, of_type, says, stopped_at_limit, uses

HELP = call("helper", "d1", task="find it")


@pytest.fixture(autouse=True)
def clean_run():
    """Forget executed tools."""
    EXECUTED.clear()
    with runtime.settings(retry_delay=0):
        yield


async def nested(script, **options):
    """Run the lead agent; return ``(result, engine, events)``."""
    options.setdefault("permissions", Permissions(mode="auto"))
    engine = Engine(llm=FakeLLM(script), **options)
    start = context("lead the work")
    result = await stopped_at_limit(engine, await engine.run(Lead(), start))
    return result, engine, engine.store.load_events(start.run_id)


async def test_nested_run_has_its_own_id_and_a_parent_on_every_event():
    """One log holds both runs, told apart by run id and agent path."""
    result, _, events = await nested(
        [uses(HELP), uses(call("lookup", "n1", key="k")), says("found"), says("end")]
    )
    assert result.answer == "end"
    child = [event for event in events if event.parent is not None]
    assert {event.parent for event in child} == {result.run_id}
    assert {event.agent for event in child} == {"lead.helper_agent"}
    assert len({event.run_id for event in child}) == 1
    assert child[0].run_id != result.run_id
    assert [event.sequence for event in events] == sorted({event.sequence for event in events})


async def test_nested_run_starts_with_a_clean_context():
    """The child sees the task text and not the parent's conversation."""
    _, engine, _ = await nested([uses(HELP), says("found"), says("end")])
    sent = engine.llm.llm.calls[1]["messages"]
    contents = [message.content for message in sent]
    assert "find it" in contents and "lead the work" not in contents


async def test_parent_reads_only_the_cut_answer():
    """The summary limit holds."""
    _, engine, _ = await nested([uses(HELP), says("x" * 1000), says("end")])
    tool_message = next(m for m in engine.llm.llm.calls[2]["messages"] if m.role == "tool")
    assert len(tool_message.content) == 40


async def test_usage_of_the_nested_run_adds_to_the_parent():
    """Three completions, three times the usage."""
    result, _, _ = await nested([uses(HELP), says("found"), says("end")])
    assert result.usage.input_tokens == 30


async def test_failed_nested_run_is_an_error_result():
    """The parent's model reads the failure and goes on."""
    with runtime.settings(max_steps=2):
        result, _, events = await nested(
            [
                uses(HELP),
                uses(call("lookup", "n1", key="k")),
                uses(call("lookup", "n2", key="k")),
                says("end"),
            ]
        )
    assert result.answer == "end"
    parent_results = [e for e in of_type(events, "tool.result") if e.parent is None]
    assert parent_results[0].is_error and "step_limit" in str(parent_results[0].output)


async def test_runlog_shows_the_nested_steps():
    """A nested step names its agent and the step that delegated it."""
    _, _, events = await nested(
        [uses(call("lookup", "p1", key="k")), uses(HELP), says("found"), says("end")]
    )
    log = gd.runlog(events)
    nested_steps = [step for step in log["steps"] if step["agent"] == "lead.helper_agent"]
    assert [step["parent"] for step in nested_steps] == [2]
    assert nested_steps[0]["llm_calls"][0]["answer"] == "found"
    assert log["run"]["usage"]["input_tokens"] == 40


async def test_nested_pause_pauses_the_parent_and_resumes_through_it():
    """One request, one answer, and the tool runs inside the nested run."""
    script = [uses(HELP), uses(call("save_note", "n1", text="x")), says("found"), says("end")]
    result, engine, events = await nested(script, permissions=Permissions(mode="ask"))
    assert (result.status, result.run_id) == ("waiting", result.run_id)
    assert len(of_type(events, "request")) == 1
    assert of_type(events, "request")[0].agent == "lead.helper_agent"
    assert EXECUTED == []

    final = await Engine(
        llm=FakeLLM(script[2:]), store=engine.store, permissions=Permissions(mode="ask")
    ).resume(result.run_id, result.request.id, {"approved": True})
    assert (final.status, final.answer) == ("done", "end")
    assert EXECUTED == ["save_note"]
    assert final.usage.input_tokens == 40


async def test_a_second_pause_in_the_nested_run_pauses_again():
    """A nested run can ask twice."""
    script = [
        uses(HELP),
        uses(call("save_note", "n1", text="x")),
        uses(call("save_note", "n2", text="y")),
        says("found"),
        says("end"),
    ]
    result, engine, _ = await nested(script, permissions=Permissions(mode="ask"))
    second = await engine.resume(result.run_id, result.request.id, {"approved": True})
    assert second.status == "waiting" and second.request.call_id == "n2"
    final = await engine.resume(result.run_id, second.request.id, {"approved": True})
    assert final.answer == "end" and EXECUTED == ["save_note", "save_note"]


async def test_recovery_finds_a_nested_pause():
    """The parent's state rebuilds from the shared log."""
    script = [uses(HELP), uses(call("save_note", "n1", text="x"))]
    result, engine, events = await nested(script, permissions=Permissions(mode="ask"))
    assert recover(events, result.run_id).pending.child is not None


async def test_replay_runs_the_nested_run_again():
    """A nested run runs again in a replay, with its own completions."""
    script = [uses(HELP), uses(call("lookup", "n1", key="k")), says("found"), says("end")]
    result, engine, _ = await nested(script)
    EXECUTED.clear()
    replayed = await Engine.replay(engine.store, result.run_id)
    assert replayed.answer == "end" and EXECUTED == ["lookup"]


async def test_public_events_of_a_nested_run_are_forwarded():
    """A publisher sees the nested request and steps."""
    seen = []

    class Publisher(gd.callbacks.Callback):
        def on_event(self, engine, event):
            if event.is_public:
                seen.append(event.type)

    await nested([uses(HELP), says("found"), says("end")], callbacks=[Publisher()])
    assert seen.count("run.started") == 2 and "run.finished" in seen
    assert "tool.result" not in seen


async def test_parent_has_no_pending_action_after_the_nested_run_ended():
    """A settled nested pause leaves nothing pending, in the step after it."""
    script = [uses(HELP), uses(call("save_note", "n1", text="x")), says("found"), says("end")]
    result, engine, _ = await nested(script, permissions=Permissions(mode="ask"))
    final = await engine.resume(result.run_id, result.request.id, {"approved": True})
    events = engine.store.load_events(final.run_id)
    finished = next(e for e in of_type(events, "step.finished") if e.parent is None)
    assert recover(events[: finished.sequence], final.run_id).pending is None


class DyingStore(MemoryRunStore):
    """Die just before the first event of one type and run is saved."""

    def __init__(self, kind, is_nested):
        """Remember what to die on."""
        super().__init__()
        self.kind = kind
        self.is_nested = is_nested

    def save_event(self, run_id, event):
        """Raise once instead of saving."""
        if event.type == self.kind and (event.parent is not None) == self.is_nested:
            self.kind = None
            raise Killed
        super().save_event(run_id, event)


class Killed(BaseException):
    """A process dying."""


async def killed_after_answer(kind, is_nested):
    """Pause in a nested run, answer, and die at one event; return the store and the request."""
    script = [uses(HELP), uses(call("save_note", "n1", text="x")), says("found"), says("end")]
    store = DyingStore(None, is_nested)
    start = context("lead the work")
    ask = Permissions(mode="ask")
    paused = await Engine(llm=FakeLLM(script), store=store, permissions=ask).run(Lead(), start)
    store.kind = kind
    with pytest.raises(Killed):
        await Engine(llm=FakeLLM(script[2:]), store=store, permissions=ask).resume(
            start.run_id, paused.request.id, {"approved": True}
        )
    return store, start.run_id, paused.request.id, script


async def test_killed_while_the_nested_run_continues_is_not_stuck():
    """The answer reached the child; a resume without arguments finishes the job."""
    store, run_id, _, script = await killed_after_answer("step.finished", True)
    fresh = Engine(llm=FakeLLM(script[2:]), store=store, permissions=Permissions(mode="ask"))
    assert (await fresh.resume(run_id)).answer == "end"


async def test_killed_after_the_nested_run_ended_is_not_stuck():
    """The child's outcome is in the log; the parent takes it from there."""
    store, run_id, request_id, script = await killed_after_answer("tool.result", False)
    fresh = Engine(llm=FakeLLM(script[3:]), store=store, permissions=Permissions(mode="ask"))
    final = await fresh.resume(run_id, request_id, {"approved": True})
    assert final.answer == "end"
    assert final.usage.input_tokens == 40


async def test_crash_in_a_nested_run_keeps_its_usage_and_ends_it():
    """The parent's model reads the interruption, and no spending is lost."""
    store = DyingStore("tool.result", True)
    start = context("lead the work")
    script = [uses(HELP), uses(call("lookup", "n1", key="k"))]
    auto = Permissions(mode="auto")
    with pytest.raises(Killed):
        await Engine(llm=FakeLLM(script), store=store, permissions=auto).run(Lead(), start)
    fresh = Engine(llm=FakeLLM([says("end")]), store=store, permissions=auto)
    result = await fresh.resume(start.run_id)
    events = store.load_events(start.run_id)
    assert result.answer == "end" and result.usage.input_tokens == 30
    nested_end = [e for e in of_type(events, "run.finished") if e.parent is not None]
    assert [e.stop_reason for e in nested_end] == ["error"]


async def test_step_usage_includes_the_nested_run():
    """The step that delegated spent what the nested run spent."""
    _, _, events = await nested([uses(HELP), says("found"), says("end")])
    parent_steps = [e for e in of_type(events, "step.finished") if e.parent is None]
    assert parent_steps[0].usage.input_tokens == 20
