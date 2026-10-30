"""One step: one agent call, the decision and dispatch of its tool calls, one checkpoint.

A step is written over the log: each part looks at the state and does only what is not recorded
yet. So a step continues from any point, after a pause or a crash, without a second LLM call.
"""

import asyncio

from swarmax.core.engine.session import Stop, is_cancel
from swarmax.core.types import RULE_MODEL, Completion, Deny, Finish, Request, ToolResult
from swarmax.core.types.events import (
    LLMCompleted,
    StepFinished,
    StepStarted,
    ToolFinished,
    ToolRecorded,
    ToolStarted,
    UsageUpdated,
)
from swarmax.errors import OutputError, ToolError, UnknownNameError
from swarmax.tools import dispatch
from swarmax.tools.dispatch import error_output
from swarmax.utils.strings import did_you_mean

SUMMARY_CHARACTERS = 200
MAX_UNKNOWN_CALLS = 2


async def record_result(session, call, result, **fields):
    """Log one result, before the model acts on it, and report the end of the tool."""
    state = session.state
    await session.emit(
        ToolRecorded,
        index=state.step,
        call_id=call.id,
        tool=call.name,
        input=call.input,
        output=result.output,
        is_error=result.is_error,
        is_validation=result.is_validation,
        duration=result.duration,
        reference=result.reference,
        usage=session.take_child_usage(),
        **fields,
    )
    await session.emit(
        ToolFinished,
        index=state.step,
        call_id=call.id,
        output_summary=str(result.output)[:SUMMARY_CHARACTERS],
        duration=result.duration,
        error=str(result.output)[:SUMMARY_CHARACTERS] if result.is_error else None,
    )


def text_result(call, text, **fields):
    """Return a result holding text."""
    return ToolResult(call_id=call.id, tool=call.name, output=text, **fields)


async def _think(session, agent):
    """Make the agent call of this step, unless the log already holds it."""
    result = await agent(session.context())
    decision = result.decision
    if isinstance(decision, Request):
        return await session.pause(decision, "llm")
    if decision is not None:
        return Stop("cancelled" if is_cancel(decision) else "denied", decision.reason)
    if session.state.action is None:
        completion = Completion(
            text=result.action.text, tool_calls=result.action.tool_calls, model=RULE_MODEL
        )
        await session.emit(
            LLMCompleted,
            index=session.state.step,
            completion=completion,
            messages=result.messages,
        )
    return None


async def _admit(session, agent, tool, call):
    """Decide one call; return a ``Stop``, ``None`` when it is settled, or the call to run."""
    decision = await session.decide(agent, tool, call)
    if isinstance(decision, Request):
        return await session.pause(decision, "tool", call)
    if is_cancel(decision):
        return Stop("cancelled", decision.reason)
    if isinstance(decision, Deny):
        result = text_result(call, decision.reason, is_error=True)
        await record_result(session, call, result, source="denied")
        return None
    return next(item for item in session.state.calls if item.id == call.id)


def _over_retries(session, tool):
    """Return the stop of a tool that failed validation too often in a row, or ``None``."""
    failures = session.state.failures.get(tool.name, 0)
    if failures < tool.max_retries:
        return None
    return Stop("error", f"{tool.name}: {failures} invalid calls in a row")


async def _reuse(session, call, recorded):
    """Record the stored result of a replay."""
    result = ToolResult(
        call_id=call.id,
        tool=call.name,
        output=recorded.output,
        is_error=recorded.is_error,
        is_validation=recorded.is_validation,
        reference=recorded.reference,
    )
    await record_result(session, call, result, source=recorded.source)


async def _execute(session, agent, tool, call):
    """Run one admitted call and handle what it returned."""
    if call.id not in session.state.started:
        await session.emit(
            ToolStarted, index=session.state.step, call_id=call.id, tool=call.name, input=call.input
        )
    recorded = session.engine.recorded.get(call.id)
    if recorded is not None and not (tool.is_pure and recorded.source == "tool"):
        await _reuse(session, call, recorded)
        return _over_retries(session, tool)
    outcome = await dispatch(tool, call)
    if isinstance(outcome, Finish):
        return await _gate_answer(session, agent, outcome.answer, call)
    if isinstance(outcome, Request) and session.waiting_child is not None:
        return await session.wait_for_child(outcome, call)
    if isinstance(outcome, Request):
        return await session.pause(outcome, "tool", call)
    await record_result(session, call, outcome)
    return _over_retries(session, tool)


async def _refuse_unknown(session, agent, call):
    """Tell the model a tool does not exist; repeating it counts as a validation failure."""
    names = agent.tools()
    error = UnknownNameError(
        f"tool = {call.name!r}; expected a tool of this agent{did_you_mean(call.name, names)}"
    )
    result = ToolResult(
        call_id=call.id,
        tool=call.name,
        output=error_output(error),
        is_error=True,
        is_validation=True,
    )
    await record_result(session, call, result)
    failures = session.state.failures.get(call.name, 0)
    return Stop("error", f"{call.name}: unknown tool") if failures >= MAX_UNKNOWN_CALLS else None


async def _run_calls(session, agent):
    """Decide and run the open calls: read and compute tools together, others in order."""
    state = session.state
    tools = agent.tools()
    calls = [call for call in state.calls if call.id not in state.results]
    is_together = all(
        call.name in tools and tools[call.name].is_pure and not tools[call.name].runs_alone
        for call in calls
    )
    admitted = []
    for call in calls:
        if call.name not in tools:
            stop = await _refuse_unknown(session, agent, call)
            if stop is not None:
                return stop
            continue
        outcome = await _admit(session, agent, tools[call.name], call)
        if isinstance(outcome, Stop):
            return outcome
        if outcome is None:
            continue
        if is_together:
            admitted.append(outcome)
            continue
        stop = await _execute(session, agent, tools[call.name], outcome)
        if stop is not None:
            return stop
    stops = await asyncio.gather(
        *(_execute(session, agent, tools[call.name], call) for call in admitted)
    )
    return next((stop for stop in stops if stop is not None), None)


async def _give_feedback(session, agent, call, text, kind):
    """Send a refused answer back to the model, as a tool result or a message."""
    if call is not None:
        result = text_result(call, text, is_error=True)
        await record_result(session, call, result, source="denied", feedback=kind)
    else:
        await session.emit(
            ToolRecorded,
            index=session.state.step,
            output=text,
            is_error=True,
            source="denied",
            feedback=kind,
        )


async def _gate_answer(session, agent, answer, call):
    """Pass a proposed answer through ``before_finish`` and the output; return a stop or ``None``.

    ``None`` with a ``finish`` call means it is recorded, and the step closes after its other
    calls. ``None`` without a call means feedback went back to the model. An accepted answer is
    logged before the run ends, so a crash in between repeats no LLM call.
    """
    state = session.state
    decision = await session.before_finish(agent, state.action)
    if isinstance(decision, Request):
        return await session.pause(decision, "finish", call)
    if is_cancel(decision):
        return Stop("cancelled", decision.reason)
    if isinstance(decision, Deny):
        await _give_feedback(session, agent, call, decision.reason, "finish")
        return None
    try:
        answer = agent.output.validate(answer)
    except OutputError as error:
        await _give_feedback(session, agent, call, str(error), "output")
        if state.output_failures > agent.output.max_retries:
            return Stop("error", str(error))
        return None
    if call is None:
        await session.emit(ToolRecorded, index=state.step, output=answer, is_finish=True)
        return Stop("answer", answer=answer)
    await record_result(session, call, text_result(call, answer), is_finish=True)
    return None


async def close_step(session):
    """Log the end of the step, the running totals and a checkpoint."""
    state = session.state
    await session.emit(StepFinished, index=state.step, usage=state.step_usage)
    await session.emit(UsageUpdated, **state.usage.model_dump())
    await session.snapshot()


async def run_step(session, agent):
    """Run or continue one step; return a ``Stop`` or ``None`` to go on."""
    state = session.state
    if not state.in_step:
        await session.emit(StepStarted, index=state.step + 1)
    if state.action is None:
        stop = await _think(session, agent)
        if stop is not None:
            return stop
    stop = await _run_calls(session, agent)
    if stop is None and state.has_answer:
        stop = Stop(state.stop_reason, answer=state.answer)
    if stop is None and not state.action.tool_calls and not state.is_refused:
        stop = await _gate_answer(session, agent, state.action.text, None)
    if stop is not None and stop.reason == "request":
        return stop
    await close_step(session)
    return stop


async def settle_interrupted(session, agent):
    """Handle calls a crash left started and unrecorded.

    An idempotent tool runs again; any other becomes an error result for the model, because
    nobody knows how far it got.
    """
    state = session.state
    tools = agent.tools()
    for call in state.calls:
        tool = tools.get(call.name)
        is_open = call.id in state.started and call.id not in state.results
        if is_open and (tool is None or not tool.idempotent):
            error = ToolError(f"{call.name}: interrupted by a crash; it may have run in part")
            result = ToolResult(
                call_id=call.id, tool=call.name, output=error_output(error), is_error=True
            )
            await record_result(session, call, result, source="interrupted")
