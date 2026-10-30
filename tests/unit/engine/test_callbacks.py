"""Callbacks observe and never change a run."""

from geomind.engine.callbacks import CALLBACK_METHODS, Callback, EventLog
from geomind.types.events import EVENT_CLASSES
from geomind.utils.json import read_lines
from tests.fixtures.runs import call, of_type, run, says, types, uses


class Recorder(Callback):
    """Record what it is told."""

    def __init__(self):
        """Start empty."""
        self.seen = []

    def on_event(self, engine, event):
        """Record every type."""
        self.seen.append(event.type)

    async def on_tool_end(self, engine, event):
        """Be asynchronous on purpose."""
        self.seen.append("async tool end")


class Failing(Callback):
    """Fail on every step."""

    def on_step_start(self, engine, event):
        """Raise."""
        raise ValueError("observer bug")


class Watcher(Callback):
    """Keep the errors it observes."""

    def __init__(self):
        """Start empty."""
        self.errors = []

    def on_error(self, engine, event):
        """Keep one error event."""
        self.errors.append(event)


class FailingOnError(Callback):
    """Fail in both methods."""

    def on_step_start(self, engine, event):
        """Raise."""
        raise ValueError("first")

    def on_error(self, engine, event):
        """Raise again."""
        raise ValueError("second")


def test_method_table_names_real_types_and_methods():
    """Every table entry exists."""
    assert set(CALLBACK_METHODS) <= set(EVENT_CLASSES)
    assert all(hasattr(Callback, name) for name in CALLBACK_METHODS.values())


async def test_on_event_sees_every_event_and_async_methods_run():
    """Both plain and ``async`` methods are called."""
    recorder = Recorder()
    _, _, events = await run([uses(call("add", left=1, right=2)), says()], callbacks=[recorder])
    assert "async tool end" in recorder.seen
    assert [item for item in recorder.seen if item != "async tool end"] == types(events)


async def test_failing_callback_never_changes_the_run():
    """The run ends as usual, and the failure is an error event for the others."""
    watcher = Watcher()
    result, _, events = await run([says("ok")], callbacks=[Failing(), watcher])
    assert result.answer == "ok"
    assert [item.where for item in watcher.errors] == ["callback on step.started"]
    assert of_type(events, "error")[0].error_class == "ValueError"


async def test_failing_on_error_does_not_loop():
    """An error in ``on_error`` is only logged."""
    result, _, events = await run([says("ok")], callbacks=[FailingOnError()])
    assert result.answer == "ok"
    assert len(of_type(events, "error")) == 2


async def test_event_log_in_memory():
    """Without a path events stay in memory."""
    log = EventLog()
    _, _, events = await run([says()], callbacks=[log])
    assert log.events == events


async def test_event_log_writes_json_lines(tmp_path):
    """With a path every event is one JSON line."""
    path = tmp_path / "events.jsonl"
    _, _, events = await run([says()], callbacks=[EventLog(path)])
    assert [line["type"] for line in read_lines(path)] == types(events)


async def test_on_event_comes_before_the_specific_method():
    """A publisher sees an event first, and internal events reach it too."""
    order = []

    class Ordered(Callback):
        def on_event(self, engine, event):
            order.append(event.type)

        def on_step_end(self, engine, event):
            order.append("specific")

    await run([says()], callbacks=[Ordered()])
    assert order.index("step.finished") + 1 == order.index("specific")
    assert "llm.completed" in order and "permission" not in order[:1]
