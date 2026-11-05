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
    earlier = _take_orphan(session, task, instance)
    if earlier is not None:
        return await _resume_child(session, earlier, agent, max_steps, beside)
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


def _task_of(event):
    """Return the task text a nested run was started with."""
    for message in event.messages[:1]:
        content = message.get("content") if isinstance(message, dict) else message.content
        return content
    return None


def _take_orphan(session, task, instance):
    """Return a nested run a crash left for this delegate call, once (QA-176, QA-188).

    ``end_orphans`` keeps the nested runs of the step the crash stopped in by their task and
    instance; the delegate call that runs again takes its own back, finished or not.
    """
    orphans = session.__dict__.get("orphans") or {}
    return orphans.pop((task, instance), None)


async def _resume_child(session, earlier, agent, max_steps, beside):
    """Go on with a nested run a crash stopped, or take the outcome of one that finished."""
    if earlier.status != "running":
        return _result_of_state(earlier)
    child = session.spawn(earlier, agent)
    child.ends_at_limit = max_steps is not None
    child.beside = beside
    session.running.add(child)
    try:
        result = await session.engine.proceed(child, None, None)
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
    """Keep the nested runs of the step a crash stopped in; end older ones and what they opened.

    A delegate call of the open step runs again (``reruns_after_crash``) and goes on with its own
    nested run, or takes the outcome of one that finished (a team mate done before the crash), so
    no finished work is lost (QA-176, QA-188). Any other open nested run is ended as interrupted,
    together with every open run below it, so none stays ``running`` (QA-184).
    """
    state = session.state
    events = session.engine.store.load_events(state.root)
    ended = {event.run_id for event in events if event.type == "run.finished"}
    starts = [event for event in events if event.type == "run.started"]
    orphans = {}
    for event in starts:
        if event.parent != state.run_id:
            continue
        if event.parent_step == state.step and state.in_step:
            orphans[(_task_of(event), event.instance)] = recover(events, event.run_id)
        elif event.run_id not in ended:
            await _end_tree(session, events, starts, ended, event.run_id)
    session.orphans = orphans


async def _end_tree(session, events, starts, ended, run_id):
    """End an open nested run and, first, every open run it started."""
    for event in starts:
        if event.parent == run_id and event.run_id not in ended:
            await _end_tree(session, events, starts, ended, event.run_id)
    orphan = recover(events, run_id)
    await session.engine.end(session.spawn(orphan, None), Stop("error", "interrupted by a crash"))
    ended.add(run_id)
    session.add_child_usage(orphan.usage)


async def end_left_orphans(session):
    """End the kept nested runs no delegate call took back, so none stays ``running``."""
    left = session.__dict__.pop("orphans", None) or {}
    if not left:
        return
    events = session.engine.store.load_events(session.state.root)
    ended = {event.run_id for event in events if event.type == "run.finished"}
    starts = [event for event in events if event.type == "run.started"]
    for orphan in left.values():
        if orphan.run_id not in ended:
            await _end_tree(session, events, starts, ended, orphan.run_id)
