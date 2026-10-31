"""Rerun a stored run offline and check that it behaves the same."""

from geomind import runtime
from geomind.agents import Agent
from geomind.context import ProblemState
from geomind.engine.context import Context
from geomind.engine.hooks import Hook
from geomind.engine.permissions import Permissions
from geomind.engine.recovery import agent_class
from geomind.errors import ReplayError
from geomind.providers import FakeLLM
from geomind.stores.run import MemoryRunStore
from geomind.types import Allow, Cancel, Deny

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

    def before_llm_call(self, context, agent, messages):
        """End the replay when no recorded completion is left; a rule step calls no model."""
        if type(agent).forward is not Agent.forward:
            return None
        return None if len(self.llm.calls) < self.scripted else Cancel(reason=END_OF_RECORDING)

    def before_tool_call(self, context, agent, call):
        """Use the recorded input, or end the replay at a call without a result."""
        recorded = self.results.get(call.id)
        if recorded is None:
            return Cancel(reason=END_OF_RECORDING)
        return Allow(input=recorded.input) if recorded.input != call.input else None

    def before_finish(self, context, agent, action):
        """Refuse the answers the original run refused."""
        reason = self.refusals.get(context.session.state.step)
        return Deny(reason=reason) if reason is not None else None


class _ReplayStore(MemoryRunStore):
    """A memory store that reads an artifact it lacks from the recorded run.

    NOTE: a reused nested run is not run again, so what its tools saved, such as a stored design,
    is read from the original store; what the replay saves itself comes first.
    """

    def __init__(self, original, run_id):
        """Keep the store and the root run id of the recording."""
        super().__init__()
        self.original = original
        self.run_id = run_id

    def load_artifact(self, run_id, key):
        """Return the replay's own artifact, else the recorded run's."""
        found = super().load_artifact(run_id, key)
        return found if found is not None else self.original.load_artifact(self.run_id, key)


def _results(events):
    """Return the tool results of a log, without feedback."""
    return [e for e in events if e.type == "tool.result" and e.call_id is not None]


def _nested_changes(events, run_id):
    """Return, by call id of the run, the problem-state changes its nested runs logged.

    A nested run is not run again in a replay; its recorded answer is reused. What it wrote in the
    shared problem state happened between the call's ``tool.started`` and ``tool.result``, so the
    replay applies those changes again with the reused answer.
    """
    started = {
        e.call_id: e.sequence for e in events if e.type == "tool.started" and e.run_id == run_id
    }
    changes = {}
    for result in _results(e for e in events if e.run_id == run_id):
        begin = started.get(result.call_id)
        changes[result.call_id] = [
            e.changes
            for e in events
            if e.type == "state.changed"
            and e.run_id != run_id
            and begin is not None
            and begin < e.sequence < result.sequence
        ]
    return changes


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
    tree = store.load_events(run_id)
    events = [event for event in tree if event.run_id == run_id]
    started = next((event for event in events if event.type == "run.started"), None)
    if started is None:
        raise ReplayError(f"replay: run = {run_id!r}; no recorded run.started")
    llm = FakeLLM.from_events(events)
    engine = engine_class(
        hooks=[_Recording(events, llm)],
        permissions=Permissions(mode="auto"),
        llm=llm,
        store=_ReplayStore(store, run_id),
    )
    engine.recorded = {event.call_id: event for event in _results(events)}
    engine.recorded_changes = _nested_changes(tree, run_id)
    context = Context(
        messages=list(started.messages),
        chat=started.chat,
        project=started.project,
        problem=ProblemState.model_validate(started.problem),
    )
    with runtime.settings(**started.settings):
        agent = agent_class(started)()
        result = await engine.run(agent, context, max_steps=started.max_steps)
    finished = next((event for event in events if event.type == "run.finished"), None)
    replayed = engine.store.load_events(context.run_id)
    _compare_calls(_results(events), _results(replayed), finished is not None)
    if finished is not None:
        _compare_end(finished, result)
    return result
