"""The export of a run for a competition report: the agent log as Markdown.

It reads the events of a run (nested runs included), never the provider: the header, every LLM
call in order, each agent's system prompt once, then the token tables and the totals. Nothing in it
depends on the clock or the run id, so a replay of a run exports the same text.
"""

import json

from geomind.agents.project.lead.comparison_driver import alternatives_table
from geomind.engine.recovery import recover
from geomind.types import RULE_MODEL, Usage

SHORT = 300
COUNTS = "LLM calls | Tokens in | Cached | Tokens out | Cost"
NOT_RECORDED = "not recorded"
FENCE = "~~~~"


def models_by_agent(events):
    """Return the model ids each agent called, in order of first use, rule steps left out."""
    models = {}
    for event in events:
        if event.type == "step.started" and event.model and event.model != RULE_MODEL:
            found = models.setdefault(event.agent, [])
            if event.model not in found:
                found.append(event.model)
    return models


def _cut(text, limit):
    """Return a text cut at ``limit`` characters."""
    return text if len(text) <= limit else f"{text[:limit]}..."


def _calls(events):
    """Return the model calls in order, each with its agent, step and run, rule steps left out."""
    calls = []
    for event in events:
        if event.type == "llm.completed" and event.completion.model != RULE_MODEL:
            calls.append(event)
    return calls


def _added(call, previous):
    """Return the messages a call added to those of the previous call of the same run.

    The answer of the previous call is part of its successor's messages and is shown with that
    call, so assistant messages are left out; so is the system prompt, printed in the appendix.
    """
    before = previous.messages if previous is not None else ()
    shared = 0
    while shared < len(before) and shared < len(call.messages):
        if before[shared] != call.messages[shared]:
            break
        shared += 1
    return [
        message
        for message in call.messages[shared:]
        if message.role != "assistant" and not (message.role == "system" and shared == 0)
    ]


def _block(text):
    """Return a text as a fenced block, so its own headings stay inside it."""
    return [FENCE, *text.splitlines(), FENCE, ""]


def _message_lines(messages):
    """Return the lines of added messages: the user's task in full, the rest in short."""
    lines = []
    for message in messages:
        text = message.content if message.role == "user" else _cut(message.content, SHORT)
        lines += [f"{message.role}:", "", *_block(text)]
    return lines


def _tool_call_lines(completion):
    """Return the lines of the tool calls an answer asks for."""
    return [
        f"- {call.name}({json.dumps(call.input, sort_keys=True)})" for call in completion.tool_calls
    ]


def _usage_text(usage):
    """Return the tokens and cost of one call."""
    return (
        f"{usage.input_tokens} in ({usage.cached_tokens} cached), {usage.output_tokens} out, "
        f"cost {usage.cost}"
    )


def _call_lines(number, call, previous):
    """Return the Markdown of one LLM call."""
    completion = call.completion
    lines = [f"### Call {number}: {call.agent}, {completion.model}", ""]
    added = _message_lines(_added(call, previous))
    lines += ["Messages added:", "", *added] if added else []
    lines += ["Answer:", "", *(_block(completion.text) if completion.text else ["(no text)", ""])]
    tools = _tool_call_lines(completion)
    lines += ["Tool calls:", "", *tools, ""] if tools else []
    return [*lines, f"Tokens: {_usage_text(completion.usage)}", ""]


def _header(events, manifest):
    """Return the header: the request, the loop, the versions and the models by role."""
    started = next(e for e in events if e.type == "run.started" and e.parent is None)
    request = next((m.content for m in reversed(started.messages) if m.role == "user"), "")
    versions = {
        name: started.versions.get(name)
        or (manifest or {}).get(name, {}).get("version", NOT_RECORDED)
        for name in ("geomind", "gemini")
    }
    lines = [
        "# Agent log",
        "",
        "## Request",
        "",
        request,
        "",
        f"Loop: {started.loop or NOT_RECORDED}",
        "",
        f"gemini version: {versions['gemini']}. geomind version: {versions['geomind']}.",
        "",
        "Models by role:",
        "",
    ]
    models = models_by_agent(events)
    lines += [f"- {agent}: {', '.join(found)}" for agent, found in models.items()]
    configured = {role: model for role, model in started.models.items() if model}
    if configured:
        lines += ["", "Models configured by role:", ""]
        lines += [f"- {role}: {model}" for role, model in configured.items()]
    return [*lines, ""]


def _prompts(calls):
    """Return each agent's system prompt, the first message of its first call."""
    found = {}
    for call in calls:
        first = call.messages[0] if call.messages else None
        if first is not None and first.role == "system":
            found.setdefault(call.agent, first.content)
    return found


def _row(name, usages):
    """Return one table row: a name, the number of calls and their tokens and cost."""
    total = sum(usages, Usage())
    return (
        f"| {name} | {len(usages)} | {total.input_tokens} | {total.cached_tokens} "
        f"| {total.output_tokens} | {round(total.cost, 6)} |"
    )


def _tables(calls):
    """Return the token tables by agent and by step, each with the total."""
    by_agent, by_step = {}, {}
    for call in calls:
        usage = call.completion.usage
        by_agent.setdefault(call.agent, []).append(usage)
        by_step.setdefault((call.run_id, call.index, call.agent), []).append(usage)
    every = [call.completion.usage for call in calls]
    separator = "|---|---|---|---|---|---|"
    return [
        "## Tokens by agent",
        "",
        f"| Agent | {COUNTS} |",
        separator,
        *(_row(agent, usages) for agent, usages in by_agent.items()),
        _row("Total", every),
        "",
        "## Tokens by step",
        "",
        f"| Step | {COUNTS} |",
        separator,
        *(
            _row(f"{number} {agent} (step {index})", usages)
            for number, ((_, index, agent), usages) in enumerate(by_step.items(), 1)
        ),
        _row("Total", every),
        "",
    ]


def _stop_lines(events):
    """Return the section of a run that a limit stopped: why, and the answer built from its record.

    A run that ended with an answer, and a log of 0.4.1 or earlier, whose stop has no answer, add
    nothing.
    """
    ended = next((e for e in events if e.type == "run.finished" and e.parent is None), None)
    if ended is None or not ended.answer or ended.stop_reason in ("answer", "finish"):
        return []
    return [
        "## Stop",
        "",
        f"Stop reason: {ended.stop_reason}. {ended.message or ''}".strip(),
        "",
        *_block(str(ended.answer)),
    ]


def _comparison_lines(events):
    """Return the table of a comparison's alternatives, or nothing for another run."""
    root = next((e for e in events if e.type == "run.started" and e.parent is None), None)
    if root is None or root.loop != "compare":
        return []
    table = alternatives_table(recover(events, root.run_id).problem.design)
    return ["## Comparison", "", table, ""] if table else []


def render_export(events, manifest=None):
    """Return the Markdown export of a run: header, every LLM call, prompts, tokens, totals.

    The versions come from the root ``run.started``. A log of 0.3.0 has none; then they come from
    ``manifest``, the run's ``run_manifest.json``, and read ``not recorded`` without one.
    """
    calls = _calls(events)
    lines = [*_header(events, manifest), "## LLM calls", ""]
    last = {}
    for number, call in enumerate(calls, 1):
        lines += _call_lines(number, call, last.get(call.run_id))
        last[call.run_id] = call
    lines += [*_stop_lines(events), *_comparison_lines(events), "## Appendix: system prompts", ""]
    for agent, text in _prompts(calls).items():
        lines += [f"### {agent}", "", *_block(text)]
    total = sum((call.completion.usage for call in calls), Usage())
    lines += [
        *_tables(calls),
        "## Totals",
        "",
        f"{len(calls)} LLM calls, {_usage_text(total)}.",
        "",
    ]
    return "\n".join(lines)
