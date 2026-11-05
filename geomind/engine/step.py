"""One step: one agent call, then the decision and dispatch of its tool calls.

A step is written over the log: each part looks at the state and does only what is not recorded
yet. So a step continues from any point, after a pause or a crash, without a second LLM call.
"""

import asyncio

from geomind import runtime
from geomind.context.compaction import context_window
from geomind.engine.compaction import compact_history
from geomind.engine.questions import answered_paths, asking_new, named_paths, reused_answer
from geomind.engine.recovery import call_key
from geomind.engine.state import Stop, is_cancel
from geomind.context.skills import first_call_skill
from geomind.errors import OutputError, ToolError, UnknownNameError
from geomind.tools import dispatch
from geomind.tools.base import with_old_names
from geomind.tools.dispatch import error_output, is_reported_error
from geomind.tools.mcp import server_of
from geomind.types import RULE_MODEL, Completion, Deny, Finish, Request, ToolResult
from geomind.types.events import (
    LLMCompleted,
    StepFinished,
    StepStarted,
    ToolFinished,
    ToolRecorded,
    ToolStarted,
    UsageUpdated,
)
from geomind.types.results import CallContext
from geomind.utils.json import to_jsonable
from geomind.utils.strings import did_you_mean

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
        mcp=server_of(call.name, call.input),
    )


def text_result(call, text, **fields):
    """Return a result holding text."""
    return ToolResult(call_id=call.id, tool=call.name, output=text, **fields)


async def answered_result(session, tool, call, text):
    """Return the result of a question a tool asked, made by the tool's ``on_answer``.

    A tool that acts on its answer (``ask_economics`` sets what the user approved) gives what the
    model reads; an error the model can act on is the result, as in ``dispatch``.
    """
    context = session.context().for_call(call.id)
    try:
        output = await tool.on_answer(context, call.input, text)
    except Exception as error:
        if not is_reported_error(error):
            raise
        return text_result(call, error_output(error), is_error=True)
    return text_result(call, to_jsonable(output))


async def _think(session, agent):
    """Make the agent call of this step, unless the log already holds it."""
    await compact_history(session, agent)
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


async def _prechecked(session, tool, call):
    """Return the error result of a call its tool's ``precheck`` refuses, or ``None`` (QA-037).

    A tool may check a call without its effect (``set_case`` runs gemini's check without storing)
    so the user is never asked to approve a call that fails. Any other failure of the check is
    left to the call itself.
    """
    check = getattr(tool, "precheck", None)
    if check is None:
        return None
    try:
        arguments = tool.validate(call.input)
        await check(session.context().for_call(call.id), **arguments)
    except Exception as error:
        if not is_reported_error(error):
            return None
        return text_result(call, error_output(error), is_error=True)
    return None


async def _admit(session, agent, tool, call):
    """Decide one call; return a ``Stop``, ``None`` when it is settled, or the call to run."""
    decision = await session.decide(agent, tool, call)
    if isinstance(decision, Request) and decision.kind == "approval":
        refused = await _prechecked(session, tool, call)
        if refused is not None:
            await record_result(session, call, with_skill(refused, session.state.messages))
            return None
    if isinstance(decision, Request):
        return await session.pause(decision, "tool", call)
    if is_cancel(decision):
        return Stop("cancelled", decision.reason)
    if isinstance(decision, Deny):
        result = text_result(call, decision.reason, is_error=True)
        await record_result(session, call, result, source="denied")
        return None
    return next(item for item in session.state.calls if item.id == call.id)


SAME_NOTE = (
    "{tool}: the same call (tool and whole input) as step {step}, and nothing was written since, "
    "so it did not run again: same result as step {step}: {shown}. Sending it again gives "
    "nothing new and, a few times in a row, ends the run: take the next step of your task."
)
"""What a model reads for a call that repeats an earlier successful one (``same_result``)."""


def same_result(session, agent, tool, call):
    """Return the note for a call identical to an earlier successful one of the run, or ``None``.

    Only a tool that ``repeats_same`` qualifies (a pure tool, or a write that sets its input such
    as ``set_ranges``), and only when no call of a tool that is not pure ran with success since:
    a write, a nested run or a server's tool may change what the call reads, so then it runs
    again. A design lead sent one ``set_ranges`` call 37 times, 12.7k characters each.
    NOTE: a replay takes a recorded call as recorded (``_execute`` asks only without a recorded
    result), so an older log replays as it ran.
    """
    if not tool.repeats_same:
        return None
    key = call_key(call.name, call.input)
    succeeded = session.state.succeeded
    index = next((i for i in reversed(range(len(succeeded))) if succeeded[i].key == key), None)
    if index is None:
        return None
    later = {item.tool for item in succeeded[index + 1 :]}
    tools = session.tools_of(agent, sorted(later))
    if any(name not in tools or not tools[name].is_pure for name in later):
        return None
    earlier = succeeded[index]
    shown = earlier.outline
    if earlier.reference:
        shown = f"stored as {earlier.reference}, {earlier.outline}"
    return SAME_NOTE.format(tool=call.name, step=earlier.step, shown=shown)


def _over_retries(session, tool):
    """Return the stop of a tool that failed validation too often in a row, or ``None``.

    The same call failing the same way more than the tool's ``max_retries`` times in a row stops
    the run too: the model is not learning from the error, so going on only spends. So does a
    call answered from its earlier result (``same_result``) in more steps in a row than that.
    """
    if session.state.same_calls > tool.max_retries:
        return Stop(
            "error",
            f"{tool.name}: the same call as an earlier successful one was sent in "
            f"{session.state.same_calls} steps in a row; the run stops instead of spending more",
        )
    if session.state.repeated > tool.max_retries:
        return Stop(
            "error",
            f"{tool.name}: the same call failed {session.state.repeated} times in a row with the "
            "same error; the run stops instead of spending more",
        )
    failures = session.state.failures.get(tool.name, 0)
    if failures < tool.max_retries:
        return None
    return Stop("error", f"{tool.name}: {failures} invalid calls in a row")


async def _reuse(session, tool, call, recorded):
    """Record the stored result of a replay, after the state changes its reused nested runs made."""
    key = (session.state.step, call.id)
    for changes in session.engine.recorded_changes.get(session.state.run_id, {}).get(key, ()):
        await session.change_state(list(changes))
    answered = getattr(tool, "on_answer", None)
    output = recorded.output if isinstance(recorded.output, dict) else {}
    if recorded.source == "answer" and answered is not None and "answer" in output:
        await answered_result(session, tool, call, output["answer"])
    result = ToolResult(
        call_id=call.id,
        tool=call.name,
        output=recorded.output,
        is_error=recorded.is_error,
        is_validation=recorded.is_validation,
        reference=recorded.reference,
    )
    await record_result(session, call, result, source=recorded.source)


def _runs_again(session, tool, recorded):
    """Tell whether a replay runs this tool instead of reusing its recorded result.

    NOTE: a tool that is only pure reuses its result when the replay ``reuses_tools``; a tool
    that writes the problem state (``reruns_in_replay``) still runs, since the state must follow,
    and so does the call that ended the run, which only running it can end again.
    """
    if recorded.source != "tool":
        return False
    reuses = session.engine.reuses_tools and not recorded.is_finish
    return tool.reruns_in_replay or (tool.is_pure and not reuses)


async def _execute(session, agent, tool, call):
    """Run one admitted call and handle what it returned."""
    if call.id not in session.state.started:
        await session.emit(
            ToolStarted,
            index=session.state.step,
            call_id=call.id,
            tool=call.name,
            input=call.input,
            mcp=server_of(call.name, call.input),
        )
    results = session.engine.recorded.get(session.state.run_id, {})
    recorded = results.get((session.state.step, call.id))
    if recorded is not None and not _runs_again(session, tool, recorded):
        await _reuse(session, tool, call, recorded)
        return _over_retries(session, tool)
    same = same_result(session, agent, tool, call) if recorded is None else None
    if same is not None:
        await record_result(session, call, text_result(call, same), source="repeat")
        return _over_retries(session, tool)
    outcome = await dispatch(tool, call, session.context())
    if isinstance(outcome, Finish):
        session.proposed_suggestions = outcome.suggestions
        return await _gate_answer(session, agent, outcome.answer, call)
    if isinstance(outcome, Request) and session.waiting_child is not None:
        return await session.wait_for_child(outcome, call)
    if isinstance(outcome, Request):
        found = answered_paths(session.engine.store.load_events(session.state.root), outcome)
        if found and set(found) == named_paths(outcome.message):
            await record_result(session, call, text_result(call, reused_answer(found)))
            return _over_retries(session, tool)
        return await session.pause(asking_new(outcome, found) if found else outcome, "tool", call)
    await record_result(session, call, with_skill(outcome, session.state.messages))
    return _over_retries(session, tool)


def with_skill(result, messages):
    """Return ``result`` with its tool's skill attached on the tool's first call (``first_call_skill``).

    A text output gets the skill after it, a dict one a ``skill`` key; any other output is left.
    """
    text = first_call_skill(result.tool, messages)
    if text is None:
        return result
    if isinstance(result.output, str):
        return result.model_copy(update={"output": f"{result.output}\n\n{text}"})
    if isinstance(result.output, dict) and "skill" not in result.output:
        return result.model_copy(update={"output": {**result.output, "skill": text}})
    return result


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


async def _refuse_hidden(session, call):
    """Answer a call of a tool the run does not offer (the memory is off) without running it.

    NOTE: no validation failure: the model named a tool from its prompt, and the answer says why.
    """
    reason = session.missing_services(session.agent).get(call.name)
    text = (
        f"{call.name}: {reason}, so {call.name} is not offered; go on without it"
        if reason
        else f"{call.name}: the memory is off for this run (GEOMIND_MEMORY), so {call.name} is not "
        "offered; call no memory tool and go on without it"
    )
    error = ToolError(text, code="not_allowed")
    result = ToolResult(call_id=call.id, tool=call.name, output=error_output(error), is_error=True)
    await record_result(session, call, result)


def _runs_together(tool):
    """Tell whether a tool runs beside the other calls of its step."""
    return (tool.is_pure or getattr(tool, "runs_beside", False)) and not tool.runs_alone


async def _run_calls(session, agent):
    """Decide and run the open calls: read and compute tools together, others in order."""
    state = session.state
    await session.ensure_mcp()
    calls = [call for call in state.calls if call.id not in state.results]
    tools = session.tools_of(agent, [call.name for call in calls])
    hidden = session.hidden_tools(agent)
    is_together = all(call.name in tools and _runs_together(tools[call.name]) for call in calls)
    admitted = []
    for call in calls:
        if call.name not in tools:
            stop = await _refuse_unknown(session, agent, call)
            if stop is not None:
                return stop
            continue
        if call.name in hidden:
            await _refuse_hidden(session, call)
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
    unfinished = agent.answer_problem(session.context())
    if unfinished:
        await _give_feedback(session, agent, call, unfinished, "finish")
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


def call_context(state):
    """Return the context of the step's provider call, or ``None`` when it made none."""
    used = state.call_input_tokens
    if used is None:
        return None
    window = state.context_window
    return CallContext(
        used=used, window=window, remaining=None if window is None else window - used
    )


async def report_usage(session):
    """Send the running totals of the run."""
    usage = session.state.usage
    await session.emit(
        UsageUpdated,
        input_tokens=usage.input_tokens,
        output_tokens=usage.output_tokens,
        cost=usage.cost,
    )


async def close_step(session):
    """Log the end of the step, with its own calls' usage and context, then the running totals.

    ``usage`` of ``step.finished`` is the step's own model calls only; what its nested runs spent
    joins the running totals of the ``usage`` event.
    """
    state = session.state
    await session.emit(
        StepFinished,
        index=state.step,
        usage=state.call_usage,
        text=state.action.text if state.action else "",
        context=call_context(state),
        loop_state=session.loop_state(),
    )
    await report_usage(session)


async def run_step(session, agent):
    """Run or continue one step; return a ``Stop`` or ``None`` to go on."""
    state = session.state
    await session.ensure_mcp()
    if not state.in_step:
        model = agent.model.resolved_name()
        await session.emit(
            StepStarted,
            index=state.step + 1,
            model=model,
            session=state.run_id,
            context_window=None if model == RULE_MODEL else context_window(model),
        )
    if state.action is None:
        stop = await _think(session, agent)
        if stop is not None:
            return stop
    if state.is_cut and not state.results:
        await _retry_cut(session, agent)
        await close_step(session)
        return None
    stop = await _run_calls(session, agent)
    if stop is None and state.has_answer:
        stop = Stop(state.stop_reason, answer=state.answer)
    if stop is None and not state.action.tool_calls and not state.is_refused:
        stop = await _gate_answer(session, agent, state.action.text, None)
    if stop is not None and stop.reason == "request":
        return stop
    await close_step(session)
    return stop


CUT_NOTE = (
    "Your last answer stopped at the output limit of one call ({limit} tokens) and was cut, so "
    "nothing of it ran. Answer again, shorter: think less, and make one small tool call."
)
"""What a model reads after a completion the output limit cut."""

EARLY_CUT_NOTE = (
    "The provider ended your last answer early: it reported the output limit after {tokens} of "
    "{limit} tokens, so nothing of it ran. Your answer was not too long: send the same step "
    "again, one tool call."
)
"""What a model reads after a completion the provider ended far below the limit (QA-012)."""


async def _retry_cut(session, agent):
    """Tell the model its cut completion did not run; each cut call gets the note as its result."""
    limit = runtime.get("max_output_tokens")
    tokens = session.state.cut_tokens
    early = isinstance(limit, int) and tokens < limit // 2
    note = EARLY_CUT_NOTE.format(tokens=tokens, limit=limit) if early else CUT_NOTE.format(limit=limit)
    calls = session.state.calls
    if not calls:
        await session.emit(
            ToolRecorded,
            index=session.state.step,
            output=note,
            is_error=True,
            source="denied",
            feedback="length",
        )
        return
    for call in calls:
        result = text_result(call, note, is_error=True)
        await record_result(session, call, result, source="denied", feedback="length")


async def settle_interrupted(session, agent):
    """Handle calls a crash left started and unrecorded.

    An idempotent tool runs again, and so does a nested agent (``reruns_after_crash``: a
    ``Delegate`` or ``Team``, whose open nested run ``end_orphans`` ended): it is asked again with
    the same brief, never failed at once (QA-070). Any other becomes an error result for the
    model, because nobody knows how far it got.
    """
    state = session.state
    tools = with_old_names(agent.tools())
    for call in state.calls:
        tool = tools.get(call.name)
        is_open = call.id in state.started and call.id not in state.results
        reruns = tool is not None and (tool.idempotent or getattr(tool, "reruns_after_crash", False))
        if is_open and not reruns:
            error = ToolError(
                f"{call.name}: interrupted by a crash; it may have run in part", code="internal"
            )
            result = ToolResult(
                call_id=call.id, tool=call.name, output=error_output(error), is_error=True
            )
            await record_result(session, call, result, source="interrupted")
