"""Nested runs: starting one, passing an answer down, and cleaning up after a crash.

A nested run shares the root's log. ``tools/delegate.py`` stays the tool; everything the engine does
for it is here.
"""

from geomind import runtime
from geomind.engine.context import Context
from geomind.engine.recovery import recover
from geomind.engine.state import RunState, Stop
from geomind.engine.step import record_result, text_result
from geomind.errors import ToolError
from geomind.tools.dispatch import error_output
from geomind.types import Message, RunResult


async def run_child(session, agent, task, max_steps=None, beside=False, instance=None):
    """Run ``agent`` as a nested run with a clean context: the task text only.

    ``max_steps`` gives the nested run its own step limit, at which it ends and answers from
    what it has instead of asking to continue; unset, it takes the run's ``max_steps`` and asks.
    """
    state = session.state
    context = Context(
        run_id=session.engine.recorded_children.get((state.run_id, state.step, task)),
        messages=[Message(role="user", content=task)],
        chat=state.chat,
        project=state.project,
        problem=state.problem,
    )
    child = session.spawn(RunState(root=state.root), agent)
    child.ends_at_limit = max_steps is not None
    child.beside = beside
    child.state.instance = instance
    await child.start(
        context,
        max_steps=max_steps or runtime.get("max_steps"),
        parent=state.run_id,
        parent_step=state.step,
        root=state.root,
    )
    session.running.add(child)
    try:
        result = await session.engine.drive(child)
    finally:
        session.running.discard(child)
    session.child_limit = child.limit_reached
    return result


def _result_of_state(state):
    """Return the result of a run that already ended."""
    return RunResult(
        run_id=state.run_id,
        status=state.status,
        answer=state.answer,
        usage=state.usage,
        steps=state.step,
        stop_reason=state.stop_reason,
        message=None if state.stop_reason == "error" else state.message,
    )


async def answer_child(session, pending, request_id, answer):
    """Pass an answer to the nested run that asked; its outcome is the tool result.

    A crash can come after the answer reached the nested run. The log then shows it holds no
    request, so it continues without one, or has ended, so its outcome stands.
    """
    engine = session.engine
    tool = session.agent.tools()[pending.call.name]
    state = recover(engine.store.load_events(session.state.root), pending.child)
    if state.status != "running":
        result = _result_of_state(state)
    else:
        child = session.spawn(state, tool.agent)
        result = await engine.proceed(
            child, *((None, None) if state.pending is None else (request_id, answer))
        )
        session.child_limit = child.limit_reached
    session.add_child_usage(result.usage)
    return await _finish_delegate(session, pending, tool, result)


async def _finish_delegate(session, pending, tool, result):
    """Turn the outcome of a nested run into the result of the delegate call."""
    try:
        outcome = tool.outcome(result, session.child_limit)
    except ToolError as error:
        failed = text_result(pending.call, error_output(error), is_error=True)
        await record_result(session, pending.call, failed)
        return None
    if result.request is not None:
        session.waiting_child = result.run_id
        return await session.wait_for_child(outcome, pending.call)
    task = (pending.call.input or {}).get("task") if isinstance(pending.call.input, dict) else None
    if hasattr(tool, "record_finding") and task:
        await tool.record_finding(session, task, result)
    await record_result(session, pending.call, text_result(pending.call, outcome))
    return None


async def end_orphans(session):
    """End nested runs a crash left open, and keep what they spent for the parent."""
    state = session.state
    events = session.engine.store.load_events(state.root)
    ended = {event.run_id for event in events if event.type == "run.finished"}
    for event in events:
        is_child = event.type == "run.started" and event.parent == state.run_id
        if is_child and event.run_id not in ended:
            orphan = recover(events, event.run_id)
            await session.engine.end(
                session.spawn(orphan, None), Stop("error", "interrupted by a crash")
            )
            session.add_child_usage(orphan.usage)
