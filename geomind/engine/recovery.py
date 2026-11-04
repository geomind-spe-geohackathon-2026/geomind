"""Rebuild a run from its events: resume, crash recovery and replay are one mechanism.

``apply`` is the only code that changes run state. The engine calls it on each event as the event
is saved, and ``recover`` calls it on stored events, so the engine holds nothing the log does not.
"""

import json

from geomind.context import Compaction, ProblemState, apply_changes
from geomind.context.history import replace_older
from geomind.engine.state import PendingAction, RunState, Succeeded
from geomind.errors import RunError
from geomind.tools.stored import is_stored_form, outline, stored_form
from geomind.types import Action, Message, Usage
from geomind.types.events import LLM_EVENTS
from geomind.utils.imports import import_class
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
    state.step_grant = event.max_steps
    state.settings = dict(event.settings)
    state.messages = list(event.messages)
    state.problem = ProblemState.model_validate(event.problem)


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
    raw = completion.raw if isinstance(completion.raw, dict) else {}
    state.is_cut = raw.get("finish_reason") == "length"
    state.calls = list(completion.tool_calls)
    state.usage += completion.usage
    state.step_usage += completion.usage
    state.last_input_tokens = completion.usage.input_tokens
    state.allowed = [name for name in state.allowed if name != "llm"]


def _compaction(state, event):
    """Replace older turns by the summary, which also goes to the next run of the chat."""
    summary = event.completion.text
    state.messages = replace_older(state.messages, summary, event.turns)
    state.usage += event.completion.usage
    state.step_usage += event.completion.usage
    state.last_input_tokens = 0
    earlier = state.problem.compaction.turns if state.problem.compaction else 0
    compaction = Compaction(summary=summary, turns=earlier + event.turns)
    state.problem = state.problem.model_copy(update={"compaction": compaction})


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
    """Count validation failures of one tool in a row, and the same failing call in a row.

    A tool counts once per step: the calls of one step are sent together, before the model has
    seen any of their errors, so only a failure the model saw and repeated counts again.
    """
    _count_repeat(state, event)
    if event.is_validation:
        if state.failure_steps.get(event.tool) != state.step:
            state.failures[event.tool] = state.failures.get(event.tool, 0) + 1
        state.failure_steps[event.tool] = state.step
        return
    state.failures.pop(event.tool, None)
    state.failure_steps.pop(event.tool, None)


def _count_repeat(state, event):
    """Count how often in a row the same call failed, in steps after the model saw its error.

    A call is the same when its tool and its whole input are: three calls of one tool with
    another argument each are three calls, even when they fail with one error. The same call
    sent again in the step that first failed counts once, since the model has not seen the error.
    """
    if not event.is_error or event.call_id is None:
        state.last_failure, state.repeated = None, 0
        return
    call = next((item for item in state.calls if item.id == event.call_id), None)
    if call is None:
        return
    key = call_key(call.name, call.input)
    if key != state.last_failure:
        state.repeated = 1
    elif state.last_failure_step != state.step:
        state.repeated += 1
    state.last_failure, state.last_failure_step = key, state.step


OUTLINE_CHARACTERS = 300
"""How long the outline of a result that a repeated call is answered with is at most."""


def call_key(name, tool_input):
    """Return the key of a call: its tool and its whole input, so two calls are the same or not."""
    return json.dumps([name, tool_input], sort_keys=True, default=str)


def _count_same(state, event):
    """Remember a call that ran with success, and count the steps answered from an earlier one.

    A repeat answered in a step counts once per step, as failures do; any other result of a call
    ends the run of repeats.
    """
    if event.source == "repeat":
        if state.same_call_step != state.step:
            state.same_calls += 1
        state.same_call_step = state.step
        return
    state.same_calls, state.same_call_step = 0, None
    if event.is_error or event.is_finish or event.source != "tool":
        return
    output = to_jsonable(event.output)
    shown = output.get("summary") if is_stored_form(output, event.reference) else output
    state.succeeded.append(
        Succeeded(
            key=call_key(event.tool, event.input),
            tool=event.tool,
            step=state.step,
            reference=event.reference,
            outline=outline(shown, OUTLINE_CHARACTERS),
        )
    )


def _remember_stored(state, event):
    """Keep the short form of a result that was stored whole, for the steps after the next one."""
    if event.reference is None or is_stored_form(event.output, event.reference):
        return
    state.stored[event.call_id] = _content(stored_form(to_jsonable(event.output), event.reference))


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
    _count_same(state, event)
    if state.pending is not None and state.pending.call.id == event.call_id:
        state.pending = None
    state.results[event.call_id] = Message(
        role="tool", content=_content(event.output), tool_call_id=event.call_id
    )
    _remember_stored(state, event)
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
    if event.point == "steps":
        state.pending = None if event.request is not None else state.pending
        state.max_steps += state.step_grant if event.decision == "allow" else 0
        return
    if event.request is not None:
        if event.decision == "answer" and event.request.kind == "question":
            state.questions += 1
        state.pending = None
    if event.decision == "allow":
        state.allowed.append(event.call_id if event.point == "tool" else event.point)


def _request(state, event):
    """Hold the pending action."""
    state.pending = PendingAction(request=event.request, point=event.point, call=event.call)


def _state_changed(state, event):
    """Apply one change of the problem state."""
    state.problem = apply_changes(state.problem, event.changes)


def _step_finished(state, event):
    """Close the step."""
    state.in_step = False
    state.action = None
    state.calls = []
    state.results = {}
    state.allowed = []
    state.started = []
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
    "compaction": _compaction,
    "tool.started": _tool_started,
    "tool.result": _tool_result,
    "permission": _permission,
    "request": _request,
    "state.changed": _state_changed,
    "step.finished": _step_finished,
    "run.finished": _run_finished,
}


def apply(state, event):
    """Change ``state`` by one event of its own run."""
    handler = _HANDLERS.get(event.type)
    if handler is not None:
        handler(state, event)


def recover(events, run_id=None):
    """Return the state of a run from its events; by default, the root run.

    Nested runs share the log, so their events count for the sequence only, and for the problem
    state, which the whole tree of runs shares from the moment this run began. A delegate's usage
    comes with its result; the usage of a run that ran first for this one, without a step of it
    (the routing call), is added from its completions.
    """
    events = list(events)
    started = [event for event in events if event.type == "run.started"]
    if run_id is None and started:
        run_id = next((event.run_id for event in started if event.parent is None), None)
    if not any(event.run_id == run_id for event in started):
        raise RunError(f"recover: run = {run_id!r}; expected a log with its run.started")
    first = {e.run_id for e in started if e.parent == run_id and e.parent_step is None}
    state = RunState(run_id=run_id)
    for event in events:
        state.sequence = event.sequence
        is_shared = event.type == "state.changed" and state.root != ""
        if event.run_id == run_id or is_shared:
            apply(state, event)
        if event.run_id in first and event.type in LLM_EVENTS:
            state.usage += event.completion.usage
    return state


RENAMED_CLASSES = {
    "geomind.agents.analysis.lead.agent:AnalysisLead": "geomind.agents.analysis.lead:AnalysisLead",
    "geomind.agents.analysis.economist.agent:Economist": (
        "geomind.agents.analysis.economist:Economist"
    ),
    "geomind.agents.case.lead.agent:CaseLead": "geomind.agents.case.lead:CaseLead",
    "geomind.agents.case.geoscientist.agent:Geoscientist": (
        "geomind.agents.case.geoscientist:Geoscientist"
    ),
    "geomind.agents.design.lead.agent:DesignLead": "geomind.agents.design.lead:DesignLead",
    "geomind.agents.design.process.agent:ProcessEngineer": (
        "geomind.agents.design.process:ProcessEngineer"
    ),
    "geomind.agents.design.integration.agent:IntegrationEngineer": (
        "geomind.agents.design.integration:IntegrationEngineer"
    ),
    "geomind.agents.design.reservoir.agent:ReservoirEngineer": (
        "geomind.agents.design.reservoir:ReservoirEngineer"
    ),
    "geomind.agents.design.well.agent:WellEngineer": "geomind.agents.design.well:WellEngineer",
    "geomind.agents.design.energy.agent:EnergySystemsEngineer": (
        "geomind.agents.design.energy:EnergySystemsEngineer"
    ),
    "geomind.agents.project.lead.agent:ProjectLead": "geomind.agents.project.lead:ProjectLead",
    "geomind.agents.project.coordinator.agent:Coordinator": (
        "geomind.agents.project.coordinator:Coordinator"
    ),
    "geomind.agents.project.coordinator.agent:Answer": "geomind.agents.project.coordinator:Answer",
    "geomind.agents.project.reviewer.agent:Reviewer": "geomind.agents.project.reviewer:Reviewer",
    "geomind.agents.project.explainer.agent:Explainer": (
        "geomind.agents.project.explainer:Explainer"
    ),
    "geomind.agents.project.lead.design_driver:DesignDriver": (
        "geomind.agents.project.drivers:DesignDriver"
    ),
    "geomind.agents.project.lead.comparison_driver:CompareDriver": (
        "geomind.agents.project.comparison:CompareDriver"
    ),
    "geomind.agents.project.lead.comparison_driver:ComparisonDriver": (
        "geomind.agents.project.comparison:ComparisonDriver"
    ),
    "geomind.agents.support.lead.agent:SupportLead": "geomind.agents.support.lead:SupportLead",
    "geomind.agents.support.curator.agent:Curator": "geomind.agents.support.curator:Curator",
    "geomind.agents.support.summarizer.agent:Summarizer": (
        "geomind.agents.support.summarizer:Summarizer"
    ),
    "geomind.agents.analysis.analyst:Analyst": "geomind.agents.analysis.lead:AnalysisLead",
    "geomind.agents.formulation.formulator:Formulator": "geomind.agents.case.lead:CaseLead",
    "geomind.agents.design.designer:Designer": "geomind.agents.design.lead:DesignLead",
    "geomind.agents.verification.verifier:Verifier": ("geomind.agents.project.reviewer:Reviewer"),
    "geomind.agents.economics.economist:Economist": ("geomind.agents.analysis.economist:Economist"),
    "geomind.agents.reporting.explainer:Explainer": ("geomind.agents.project.explainer:Explainer"),
    "geomind.agents.coordination.coordinator:Coordinator": (
        "geomind.agents.project.coordinator:Coordinator"
    ),
    "geomind.agents.coordination.coordinator:Answer": ("geomind.agents.project.coordinator:Answer"),
    "geomind.loops.design:DesignDriver": ("geomind.agents.project.drivers:DesignDriver"),
    "geomind.loops.compare:CompareDriver": ("geomind.agents.project.comparison:CompareDriver"),
    "geomind.loops.compare:ComparisonDriver": (
        "geomind.agents.project.comparison:ComparisonDriver"
    ),
    "geomind.agents.general.summarizer:Summarizer": (
        "geomind.agents.support.summarizer:Summarizer"
    ),
}
"""The class path an older log names (0.4.22.dev32 or earlier), by its path now."""


def agent_class(state):
    """Return the class of the agent a run names; a renamed agent is found by its new path."""
    try:
        return import_class(RENAMED_CLASSES.get(state.agent_class, state.agent_class))
    except ImportError as error:
        raise RunError(f"recover: {error}") from error
