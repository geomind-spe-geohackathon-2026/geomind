"""Pause, crash and rebuild: the three promises of the event log."""

import pytest

from geomind import runtime
from geomind.engine import Engine, Permissions
from geomind.engine.recovery import recover
from geomind.engine.store import FileRunStore, MemoryRunStore
from geomind.errors import RunError
from geomind.providers import FakeLLM
from tests.fixtures.runs import EXECUTED, Worker, call, context, of_type, says, uses

VOLATILE = {"run", "duration"}


class Killed(BaseException):
    """A process dying: nothing in the engine catches this."""


class DyingStore(MemoryRunStore):
    """Die just before the first event of one type is saved."""

    def __init__(self, kind):
        """Remember the type to die on."""
        super().__init__()
        self.kind = kind

    def save_event(self, run_id, event):
        """Raise once instead of saving."""
        if event.type == self.kind:
            self.kind = None
            raise Killed
        super().save_event(run_id, event)


@pytest.fixture(autouse=True)
def clean_run():
    """Forget executed tools."""
    EXECUTED.clear()
    with runtime.settings(retry_delay=0):
        yield


def public_view(events):
    """Return the public events without what differs between two runs."""
    view = []
    for event in events:
        if not event.is_public or event.type == "request":
            continue
        data = {key: value for key, value in event.data().items() if key not in VOLATILE}
        view.append((event.type, data))
    return view


def script():
    """Return a run with a pause in the middle."""
    return [
        uses(call("save_note", "a", text="x"), text="saving"),
        uses(call("lookup", "b", key="k")),
        says("end"),
    ]


async def test_pause_then_a_fresh_engine_gives_the_same_run(tmp_path):
    """Resuming from files, in new objects, equals a run that never paused."""
    store = FileRunStore(tmp_path)
    first = Engine(llm=FakeLLM(script()), store=store)
    start = context()
    paused = await first.run(Worker(), start)
    assert paused.status == "waiting"

    fresh_store = FileRunStore(tmp_path)
    fresh = Engine(llm=FakeLLM(script()[1:]), store=fresh_store)
    result = await fresh.resume(start.run_id, paused.request.id, {"approved": True})

    straight = Engine(llm=FakeLLM(script()), permissions=Permissions(allow=("save_note",)))
    other = context()
    expected = await straight.run(Worker(), other)
    assert (result.answer, result.usage) == (expected.answer, expected.usage)
    assert public_view(fresh_store.load_events(start.run_id)) == public_view(
        straight.store.load_events(other.run_id)
    )
    assert EXECUTED.count("save_note") == 2


async def test_killed_between_completion_and_tools_makes_no_second_llm_call():
    """A recorded completion is reused; only what comes after it runs."""
    store = DyingStore("tool.started")
    start = context()
    with pytest.raises(Killed):
        await Engine(
            llm=FakeLLM([uses(call("lookup", key="k"))]),
            store=store,
            permissions=Permissions(mode="auto"),
        ).run(Worker(), start)
    assert EXECUTED == []

    llm = FakeLLM([says("end")])
    fresh = Engine(llm=llm, store=store, permissions=Permissions(mode="auto"))
    result = await fresh.resume(start.run_id)
    assert (result.answer, EXECUTED) == ("end", ["lookup"])
    assert len(llm.calls) == 1
    assert len(of_type(store.load_events(start.run_id), "llm.completed")) == 2
    assert [m.role for m in llm.calls[0]["messages"]][-3:] == ["assistant", "tool", "system"]


async def killed_at_the_result(tool_call):
    """Run until a tool has run and its result was not saved; return the store and the id."""
    store = DyingStore("tool.result")
    start = context()
    with pytest.raises(Killed):
        await Engine(
            llm=FakeLLM([uses(tool_call)]), store=store, permissions=Permissions(mode="auto")
        ).run(Worker(), start)
    return store, start.run_id


async def test_started_idempotent_tool_runs_again():
    """A started tool without a result is rerun when that does no harm."""
    store, run_id = await killed_at_the_result(call("save_again", text="x"))
    fresh = Engine(llm=FakeLLM([says("end")]), store=store, permissions=Permissions(mode="auto"))
    await fresh.resume(run_id)
    assert EXECUTED == ["save_again", "save_again"]


async def test_started_other_tool_becomes_an_error_for_the_model():
    """Otherwise nobody knows how far it got, and the model reads that."""
    store, run_id = await killed_at_the_result(call("save_note", text="x"))
    llm = FakeLLM([says("end")])
    fresh = Engine(llm=llm, store=store, permissions=Permissions(mode="auto"))
    result = await fresh.resume(run_id)
    assert result.answer == "end" and EXECUTED == ["save_note"]
    recorded = of_type(store.load_events(run_id), "tool.result")[0]
    assert recorded.source == "interrupted" and "interrupted" in str(recorded.output)


async def test_recovery_finds_the_pending_call_at_a_pause():
    """The pending action is in the log."""
    engine = Engine(llm=FakeLLM(script()))
    start = context()
    await engine.run(Worker(), start)
    assert recover(engine.store.load_events(start.run_id)).pending.call.id == "a"


async def test_a_finished_run_cannot_resume():
    """There is nothing left to continue."""
    engine = Engine(llm=FakeLLM([says("end")]))
    start = context()
    await engine.run(Worker(), start)
    with pytest.raises(RunError, match="already ended"):
        await engine.resume(start.run_id)


async def test_killed_after_the_last_step_of_an_answer_repeats_nothing():
    """The stop decision is in the log, so the answer stands without another LLM call."""
    store = DyingStore("run.finished")
    start = context()
    with pytest.raises(Killed):
        await Engine(llm=FakeLLM([says("end")]), store=store).run(Worker(), start)
    llm = FakeLLM([])
    result = await Engine(llm=llm, store=store).resume(start.run_id)
    assert (result.stop_reason, result.answer) == ("answer", "end")
    assert llm.calls == []


async def test_killed_after_the_last_step_of_finish_repeats_nothing():
    """The same holds for the ``finish`` tool."""
    store = DyingStore("run.finished")
    start = context()
    script = [uses(call("finish", answer="end"))]
    with pytest.raises(Killed):
        await Engine(llm=FakeLLM(script), store=store).run(Worker(), start)
    llm = FakeLLM([])
    result = await Engine(llm=llm, store=store).resume(start.run_id)
    assert (result.stop_reason, result.answer) == ("finish", "end")
    assert llm.calls == []


async def test_killed_inside_the_step_of_an_answer_repeats_nothing():
    """An accepted answer survives a crash before the step closes."""
    store = DyingStore("step.finished")
    start = context()
    with pytest.raises(Killed):
        await Engine(llm=FakeLLM([says("end")]), store=store).run(Worker(), start)
    llm = FakeLLM([])
    result = await Engine(llm=llm, store=store).resume(start.run_id)
    assert (result.stop_reason, result.answer) == ("answer", "end")


async def test_a_foreign_exception_ends_the_run_with_an_error():
    """A provider raising something else still ends the run, with a log the backend can show."""

    class Broken:
        async def complete(self, messages, tools, *, model, settings, on_text=None):
            raise OSError("connection reset")

    engine = Engine(llm=Broken())
    start = context()
    result = await engine.run(Worker(), start)
    events = engine.store.load_events(start.run_id)
    assert (result.status, result.stop_reason) == ("failed", "error")
    assert of_type(events, "error")[0].error_class == "OSError"
    assert of_type(events, "run.finished")[0].message == "connection reset"
