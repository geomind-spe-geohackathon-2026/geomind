"""Rebuild a run from its events: resume, crash recovery and replay are one mechanism.

``apply`` is the only code that changes run state. The engine calls it on each event as the event
is saved, and ``recover`` calls it on stored events, so the engine holds nothing the log does not.
"""

from geomind.engine.checkpoint import Checkpoint, PendingAction
from geomind.errors import RunError
from geomind.types import Action, Message, Usage
from geomind.utils.json import to_jsonable


def _run_started(state, event):
    """Take everything that identifies the run."""
    state.run_id = event.run_id
    state.root = event.root
    state.parent = event.parent
    state.parent_step = event.parent_step
    state.chat = event.chat
    state.project = event.project
    state.agent_class = event.agent_class
    state.agent = event.agent
    state.loop = event.loop
    state.loop_state = dict(event.loop_state)
    state.max_steps = event.max_steps
    state.settings = dict(event.settings)
    state.messages = list(event.messages)


def _step_started(state, event):
    """Open a step."""
    state.step = event.index
    state.in_step = True
    state.is_refused = False
    state.step_usage = Usage()


def _llm_completed(state, event):
    """Add the assistant message and open its tool calls."""
    completion = event.completion
    state.messages.append(
        Message(role="assistant", content=completion.text, tool_calls=completion.tool_calls)
    )
    state.action = Action(text=completion.text, tool_calls=completion.tool_calls)
    state.calls = list(completion.tool_calls)
    state.usage += completion.usage
    state.step_usage += completion.usage
    state.allowed = [name for name in state.allowed if name != "llm"]


def _tool_started(state, event):
    """Remember that a call began, for the crash rule of non-idempotent tools."""
    state.started.append(event.call_id)


def _content(output):
    """Return the text of a tool output as the model reads it."""
    return output if isinstance(output, str) else str(to_jsonable(output))


def _feedback(state, event):
    """Add feedback about the final answer to the conversation."""
    if event.call_id is None and not event.is_finish:
        state.messages.append(Message(role="user", content=_content(event.output)))
        state.is_refused = event.feedback is not None
    if event.feedback == "output":
        state.output_failures += 1


def _count_failure(state, event):
    """Count validation failures of one tool in a row."""
    if event.is_validation:
        state.failures[event.tool] = state.failures.get(event.tool, 0) + 1
        return
    state.failures.pop(event.tool, None)


def _tool_result(state, event):
    """Keep a result; the results of a step join the history together, in call order.

    NOTE: tools of one step finish in any order, while the prompt must be the same in a replay.
    """
    if event.usage is not None:
        state.usage += event.usage
        state.step_usage += event.usage
    if event.is_finish:
        state.has_answer = True
        state.answer = event.output
        state.stop_reason = "answer" if event.call_id is None else "finish"
    _feedback(state, event)
    if event.call_id is None:
        return
    _count_failure(state, event)
    if state.pending is not None and state.pending.call.id == event.call_id:
        state.pending = None
    state.results[event.call_id] = Message(
        role="tool", content=_content(event.output), tool_call_id=event.call_id
    )
    if all(call.id in state.results for call in state.calls):
        state.messages.extend(state.results[call.id] for call in state.calls)


def _replace_input(state, event):
    """Replace the input of a call by the one a hook gave."""
    state.calls = [
        call.model_copy(update={"input": event.input}) if call.id == event.call_id else call
        for call in state.calls
    ]


def _permission(state, event):
    """Apply a decision, an answer to a request, or a wait on a nested run."""
    if event.input is not None:
        _replace_input(state, event)
    if event.decision == "wait":
        state.pending = PendingAction(
            request=event.request, point=event.point, call=event.call, child=event.child
        )
        return
    if event.request is not None:
        state.pending = None
    if event.decision == "allow":
        state.allowed.append(event.call_id if event.point == "tool" else event.point)


def _request(state, event):
    """Hold the pending action."""
    state.pending = PendingAction(request=event.request, point=event.point, call=event.call)


def _step_finished(state, event):
    """Close the step."""
    state.in_step = False
    state.action = None
    state.calls = []
    state.results = {}
    state.allowed = []
    state.started = []


def _checkpoint(state, event):
    """Take the state of the loop."""
    state.loop_state = dict(event.loop_state)


def _run_finished(state, event):
    """Record how the run ended."""
    state.status = event.status
    state.stop_reason = event.stop_reason
    state.message = event.message
    state.answer = event.answer


_HANDLERS = {
    "run.started": _run_started,
    "step.started": _step_started,
    "llm.completed": _llm_completed,
    "tool.started": _tool_started,
    "tool.result": _tool_result,
    "permission": _permission,
    "request": _request,
    "step.finished": _step_finished,
    "checkpoint": _checkpoint,
    "run.finished": _run_finished,
}


def apply(state, event):
    """Change ``state`` by one event of its own run."""
    handler = _HANDLERS.get(event.type)
    if handler is not None:
        handler(state, event)
    state.created = event.time


def catch_up(state, events):
    """Apply the events after the snapshot; nested runs count for the sequence only."""
    for event in events:
        if event.sequence <= state.sequence:
            continue
        state.sequence = event.sequence
        if event.run_id == state.run_id:
            apply(state, event)
    return state


def recover(events, run_id=None):
    """Return the state of a run from its events alone; by default, the root run."""
    events = list(events)
    started = [event for event in events if event.type == "run.started"]
    if run_id is None and started:
        run_id = next((event.run_id for event in started if event.parent is None), None)
    if not any(event.run_id == run_id for event in started):
        raise RunError(f"recover: run = {run_id!r}; expected a log with its run.started")
    return catch_up(Checkpoint(run_id=run_id), events)
