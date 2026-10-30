"""Rerun a stored run offline and check that it behaves the same."""

from swarmax import runtime
from swarmax.engine.checkpoint import import_class
from swarmax.engine.context import Context
from swarmax.engine.hooks import Hook
from swarmax.engine.permissions import Permissions
from swarmax.engine.store import MemoryRunStore
from swarmax.errors import ReplayError
from swarmax.providers import FakeLLM
from swarmax.types import Allow, Cancel, Deny

END_OF_RECORDING = "end of the recording"


class _Recording(Hook):
    """Repeat what the original run decided, and stop where its log ends.

    Permissions and hooks of the original run are not repeated: the log holds their outcome. A
    call without a recorded result ends the replay, so a paused run never runs its pending tool.
    """

    def __init__(self, events, llm):
        """Index the decisions of the log."""
        self.llm = llm
        self.scripted = len(llm.completions)
        self.results = {e.call_id: e for e in _results(events)}
        self.refusals = {
            e.index: e.output
            for e in events
            if e.type == "tool.result" and e.call_id is None and e.feedback == "finish"
        }

    def before_llm_call(self, agent, messages):
        """End the replay when no recorded completion is left."""
        return None if len(self.llm.calls) < self.scripted else Cancel(reason=END_OF_RECORDING)

    def before_tool_call(self, agent, call):
        """Use the recorded input, or end the replay at a call without a result."""
        recorded = self.results.get(call.id)
        if recorded is None:
            return Cancel(reason=END_OF_RECORDING)
        return Allow(input=recorded.input) if recorded.input != call.input else None

    def before_finish(self, agent, action):
        """Refuse the answers the original run refused."""
        reason = self.refusals.get(runtime.active_run().state.step)
        return Deny(reason=reason) if reason is not None else None


def _results(events):
    """Return the tool results of a log, without feedback."""
    return [e for e in events if e.type == "tool.result" and e.call_id is not None]


def _signature(event):
    """Return what must match: the step, the call and what came back."""
    return event.index, event.tool, event.input, event.output, event.is_error


def _compare_calls(recorded, replayed, is_complete):
    """Raise for the first call that differs."""
    for old, new in zip(recorded, replayed):
        if _signature(old) != _signature(new):
            raise ReplayError(
                f"replay: step {old.index}: tool {old.tool}: recorded {_signature(old)}, "
                f"replayed {_signature(new)}"
            )
    if is_complete and len(recorded) != len(replayed):
        index = recorded[min(len(recorded), len(replayed)) - 1].index if recorded else 0
        raise ReplayError(
            f"replay: step {index}: recorded {len(recorded)} calls, replayed {len(replayed)}"
        )


def _compare_end(finished, result):
    """Raise when a run that ended with an answer ends differently."""
    if finished.stop_reason not in ("answer", "finish"):
        return
    if (finished.stop_reason, finished.answer) != (result.stop_reason, result.answer):
        raise ReplayError(
            f"replay: step {result.steps}: recorded answer {finished.answer!r}, "
            f"replayed {result.answer!r} ({result.stop_reason})"
        )


async def replay_run(engine_class, store, run_id):
    """Rerun a stored run with its recorded completions, without network.

    ``read`` and ``compute`` tools run again; others reuse their recorded results, as do calls that
    were denied or answered by the user. A difference raises ``ReplayError`` naming the first
    differing step.
    """
    events = [event for event in store.load_events(run_id) if event.run_id == run_id]
    started = next((event for event in events if event.type == "run.started"), None)
    if started is None:
        raise ReplayError(f"replay: run = {run_id!r}; no recorded run.started")
    llm = FakeLLM.from_events(events)
    engine = engine_class(
        hooks=[_Recording(events, llm)],
        permissions=Permissions(mode="auto"),
        llm=llm,
        store=MemoryRunStore(),
    )
    engine.recorded = {event.call_id: event for event in _results(events)}
    context = Context(messages=list(started.messages), chat=started.chat, project=started.project)
    with runtime.settings(**started.settings):
        agent = import_class(started.agent_class)()
        result = await engine.run(agent, context, max_steps=started.max_steps)
    finished = next((event for event in events if event.type == "run.finished"), None)
    replayed = engine.store.load_events(context.run_id)
    _compare_calls(_results(events), _results(replayed), finished is not None)
    if finished is not None:
        _compare_end(finished, result)
    return result
