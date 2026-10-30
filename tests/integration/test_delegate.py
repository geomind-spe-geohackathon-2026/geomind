"""A nested run: its id, its events, its sandbox, its pause and its place in the log."""

import pytest

import swarmax as sx
from swarmax.core import runtime
from swarmax.core.engine import Engine, Permissions
from swarmax.core.engine.checkpoint import Checkpoint
from swarmax.core.engine.recovery import recover
from swarmax.providers import FakeLLM
from swarmax.sandbox import LocalSandbox
from tests.fixtures.runs import EXECUTED, Lead, call, context, of_type, says, uses

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
    result = await engine.run(Lead(), start)
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
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


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


async def test_nested_run_has_its_own_sandbox(tmp_path):
    """Parent and child do not share a sandbox, and both close."""
    _, _, events = await nested(
        [
            uses(call("run_python", "p1", code="print(1)")),
            uses(HELP),
            uses(call("run_python", "n1", code="print(2)")),
            says("found"),
            says("end"),
        ],
        sandbox=LocalSandbox(tmp_path),
    )
    runs = [event.run_id for event in of_type(events, "sandbox.provisioned")]
    assert len(runs) == 2 and len(set(runs)) == 2
    assert len(of_type(events, "sandbox.closed")) == 2


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
    log = sx.runlog(events)
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

    checkpoint = engine.store.load_checkpoint(result.run_id)
    final = await Engine(
        llm=FakeLLM(script[2:]), store=engine.store, permissions=Permissions(mode="ask")
    ).resume(checkpoint, result.request.id, {"approved": True})
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
    first = engine.store.load_checkpoint(result.run_id)
    second = await engine.resume(first, result.request.id, {"approved": True})
    assert second.status == "waiting" and second.request.call_id == "n2"
    checkpoint = engine.store.load_checkpoint(result.run_id)
    final = await engine.resume(checkpoint, second.request.id, {"approved": True})
    assert final.answer == "end" and EXECUTED == ["save_note", "save_note"]


async def test_recovery_equals_the_checkpoint_with_a_nested_pause():
    """The parent's state rebuilds from the shared log."""
    script = [uses(HELP), uses(call("save_note", "n1", text="x"))]
    result, engine, events = await nested(script, permissions=Permissions(mode="ask"))
    saved = Checkpoint.load(engine.store.load_checkpoint(result.run_id))
    assert recover(events, result.run_id) == saved
    assert saved.pending.child is not None


async def test_replay_reuses_the_nested_result():
    """A nested run is not run again in a replay."""
    script = [uses(HELP), uses(call("lookup", "n1", key="k")), says("found"), says("end")]
    result, engine, _ = await nested(script)
    EXECUTED.clear()
    replayed = await Engine.replay(engine.store, result.run_id)
    assert replayed.answer == "end" and EXECUTED == []


async def test_public_events_of_a_nested_run_are_forwarded():
    """A publisher sees the nested request and steps."""
    seen = []

    class Publisher(sx.callbacks.Callback):
        def on_event(self, engine, event):
            if event.is_public:
                seen.append(event.type)

    await nested([uses(HELP), says("found"), says("end")], callbacks=[Publisher()])
    assert seen.count("run.started") == 2 and "run.finished" in seen
    assert "tool.result" not in seen
