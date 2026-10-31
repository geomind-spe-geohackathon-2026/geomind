"""The command line: run, chat, replay and show."""

import argparse
import asyncio
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from geomind import agents, runtime
from geomind.agents import Route
from geomind.context import ProblemState, render
from geomind.engine import Engine, Permissions, callbacks
from geomind.errors import GeomindError, RunError
from geomind.providers import FakeLLM, OpenRouter, Recorder
from geomind.run import LOOPS, Run, loop_of
from geomind.sandbox import DockerSandbox, LocalSandbox
from geomind.stores import FileWorkspace
from geomind.stores.run import FileRunStore
from geomind.types import RULE_MODEL, Message
from geomind.types.runlog import runlog

RUNS_FOLDER = ".runs"
MESSAGE_CHARACTERS = 2000
COUNTS = "LLM calls | Tokens in | Tokens out | Cost"


class _Printer(callbacks.Callback):
    """Print text as it streams, and tools as they run."""

    def on_text(self, engine, event):
        """Print a piece of text."""
        print(event.text, end="", flush=True)

    def on_tool_start(self, engine, event):
        """Print the start of a tool."""
        print(f"\n[{event.agent}] {event.tool} {json.dumps(event.input)}", flush=True)

    def on_tool_end(self, engine, event):
        """Print the end of a tool."""
        print(f"  -> {event.error or event.output_summary}", flush=True)


def _ask(request):
    """Ask in the terminal and return the answer of the contract."""
    if request.kind == "question":
        choices = [f"{option.value} ({option.label})" for option in request.options or ()]
        options = f" {choices}" if choices else ""
        return {"text": input(f"\n{request.message}{options}\n> ")}
    if input(f"\n{request.message} [y/N] ").strip().lower() in ("y", "yes"):
        return {"approved": True}
    return {"approved": False, "reason": input("Reason: ")}


def _sandbox(name):
    """Return the chosen sandbox provider."""
    return {"local": LocalSandbox, "docker": DockerSandbox, None: lambda: None}[name]()


def _changes(args):
    """Return the runtime settings the options change."""
    changes = {}
    if args.model:
        changes["default_model"] = args.model
    if args.max_steps:
        changes["max_steps"] = args.max_steps
    return changes


def _run_provider(args):
    """Return the provider of ``run``: OpenRouter, or a recording; ``--record`` keeps a copy."""
    llm = FakeLLM.from_recording(args.recording) if args.recording else OpenRouter()
    return Recorder(llm, Path(args.record)) if args.record else llm


def _command_run(args):
    """Run one message, asking in the terminal when the run pauses.

    Without ``--loop`` the coordinator routes the message; ``--loop`` names the loop instead.
    """
    workspace, project = _project(args.project)
    with runtime.settings(**_changes(args)):
        run = Run(
            message=args.message,
            project=project,
            llm=_run_provider(args),
            store=FileRunStore(RUNS_FOLDER),
            workspace=workspace,
            sandbox=_sandbox(args.sandbox),
            permissions=Permissions(mode=args.mode),
            callbacks=[_Printer()],
        )
        if args.loop is not None:
            run.loop = loop_of(Route(kind="loop", loop=args.loop))
        result = run.start()
        while result.status == "waiting":
            result = run.resume(result.request.id, _ask(result.request))
    print(f"\n\nrun {result.run_id}: {result.status} ({result.stop_reason})")
    usage = result.usage
    print(f"tokens {usage.input_tokens} in, {usage.output_tokens} out; cost {usage.cost}")
    return 0 if result.status == "done" else 1


@dataclass
class _Chat:
    """One terminal chat with one agent; ``last_run`` is what ``/log`` shows."""

    agent: str
    llm: object
    store: FileRunStore
    workspace: FileWorkspace | None
    project: str | None
    id: str = ""
    last_run: str | None = None


def _chat_provider(args):
    """Return the provider of a chat: OpenRouter, or a recording."""
    if args.live:
        return OpenRouter()
    if args.recording is None:
        raise RunError("chat: expected --live or --recording FILE")
    return FakeLLM.from_recording(args.recording)


def _project(path):
    """Return the workspace and the project of a project folder."""
    if path is None:
        return None, None
    folder = Path(path)
    return FileWorkspace(folder.parent), folder.name


def _state_text(chat):
    """Return the problem state of a chat as the model reads it."""
    stored = chat.store.load_state(chat.id)
    text = render(ProblemState.model_validate(stored)) if stored else ""
    return text or "(the problem state is empty)"


def _chat_turn(chat, message):
    """Answer one message, asking in the terminal, and keep it in the chat's history."""
    run = Run(
        message,
        chat=chat.id,
        project=chat.project,
        history=chat.store.load_history(chat.id),
        llm=chat.llm,
        store=chat.store,
        workspace=chat.workspace,
        permissions=Permissions(mode="ask"),
        callbacks=[_Printer()],
        agent=agents.named(chat.agent),
    )
    result = run.start()
    while result.status == "waiting":
        result = run.resume(result.request.id, _ask(result.request))
    chat.last_run = result.run_id
    chat.store.add_message(chat.id, Message(role="user", content=message))
    chat.store.add_message(chat.id, Message(role="assistant", content=str(result.answer or "")))
    print(f"\n[{result.status}: {result.stop_reason}]\n{_state_text(chat)}")


def _chat_command(chat, command):
    """Do one ``/`` command; return ``False`` to leave."""
    if command == "/quit":
        return False
    if command == "/state":
        print(_state_text(chat))
    elif command == "/log" and chat.last_run is not None:
        print(render_log(runlog(chat.store.load_events(chat.last_run)), False))
    elif command == "/log":
        print("(no turn yet)")
    elif command == "/reset":
        chat.id = uuid4().hex
        chat.last_run = None
    else:
        print("commands: /state, /log, /reset, /quit")
    return True


def _command_chat(args):
    """Talk to one agent in the terminal; every run is saved like ``geomind run``."""
    agents.named(args.agent)
    workspace, project = _project(args.project)
    llm = _chat_provider(args)
    chat = _Chat(args.agent, llm, FileRunStore(RUNS_FOLDER), workspace, project, uuid4().hex)
    with runtime.settings(**_changes(args)):
        while True:
            try:
                message = input("\n> ").strip()
            except EOFError:
                return 0
            is_command = message.startswith("/")
            if is_command and not _chat_command(chat, message):
                return 0
            if message and not is_command:
                _chat_turn(chat, message)


def _split_run_folder(folder):
    """Return the store and the run id of a run folder."""
    path = Path(folder)
    return FileRunStore(path.parent), path.name


def _command_replay(args):
    """Rerun a stored run offline and print pass or the first mismatch."""
    store, run_id = _split_run_folder(args.run)
    result = asyncio.run(Engine.replay(store, run_id))
    print(f"pass: {result.steps} steps, stop reason {result.stop_reason}")
    return 0


def _cut(value):
    """Return a value as text of a readable size."""
    text = value if isinstance(value, str) else json.dumps(value)
    return text if len(text) <= MESSAGE_CHARACTERS else f"{text[:MESSAGE_CHARACTERS]}..."


def _llm_lines(llm_call, heading):
    """Return the lines of one LLM call."""
    lines = [
        f"{heading}LLM call: {llm_call['model']}, {llm_call['input_tokens']} tokens in, "
        f"{llm_call['output_tokens']} out, cost {llm_call['cost']}"
    ]
    lines += [f"  {item['role']}: {_cut(item['content'])}" for item in llm_call["messages"]]
    lines.append(f"  answer: {_cut(llm_call['answer'])}")
    return lines


def _tool_lines(tool_call, heading):
    """Return the lines of one tool call."""
    status = " (error)" if tool_call.get("error") else ""
    return [
        f"{heading}Tool {tool_call['tool']}{status}: {tool_call['duration']:.3f} s",
        f"  input: {_cut(tool_call['input'])}",
        f"  output: {_cut(tool_call['output'])}",
    ]


def render_log(log, is_markdown):
    """Return the text of a run log: steps, then totals; Markdown is the export of a report."""
    if is_markdown:
        return render_markdown(log)
    run = log["run"]
    lines = [f"Run {run['id']}: {run['status']}"]
    for step in log["steps"]:
        parent = f", delegated by step {step['parent']}" if step["parent"] is not None else ""
        lines.append(f"Step {step['index']} ({step['agent']}{parent})")
        for llm_call in step["llm_calls"]:
            lines += _llm_lines(llm_call, "- ")
        for tool_call in step["tool_calls"]:
            lines += _tool_lines(tool_call, "- ")
    usage = run["usage"]
    lines.append(
        f"Totals: {usage['input_tokens']} tokens in, {usage['output_tokens']} out, "
        f"cost {usage['cost']}"
    )
    return "\n".join(lines)


def _token_row(name, calls):
    """Return one table row: a name, the number of model calls and their tokens and cost.

    NOTE: a rule step is logged as a completion of the model ``rule``; it calls no model, so it is
    not counted.
    """
    calls = [call for call in calls if call["model"] != RULE_MODEL]
    tokens_in = sum(call["input_tokens"] for call in calls)
    tokens_out = sum(call["output_tokens"] for call in calls)
    cost = round(sum(call["cost"] for call in calls), 6)
    return f"| {name} | {len(calls)} | {tokens_in} | {tokens_out} | {cost} |"


def _token_tables(log):
    """Return the tables of tokens by agent and by step, each with the total."""
    by_agent, every = {}, []
    step_rows = []
    for number, step in enumerate(log["steps"], 1):
        calls = list(step["llm_calls"])
        by_agent.setdefault(step["agent"], []).extend(calls)
        every += calls
        models = ", ".join(sorted({call["model"] for call in calls})) or "none"
        delegated = step["parent"] if step["parent"] is not None else ""
        step_rows.append(
            _token_row(
                f"{number} | {step['index']} | {step['agent']} | {delegated} | {models}", calls
            )
        )
    head = f"| Agent | {COUNTS} |"
    step_head = f"| # | Step | Agent | Delegated by step | Model | {COUNTS} |"
    agents = [_token_row(name, calls) for name, calls in by_agent.items()]
    total = _token_row("Total", every)
    return [
        "## Tokens by agent",
        "",
        head,
        "|---|---|---|---|---|",
        *agents,
        total,
        "",
        "## Tokens by step",
        "",
        step_head,
        "|---|---|---|---|---|---|---|---|---|",
        *step_rows,
        _token_row("Total | | | |", every),
        "",
    ]


def _prompts(log):
    """Return each agent's system prompt, the first part of its first LLM call."""
    found = {}
    for step in log["steps"]:
        for call in step["llm_calls"]:
            first = call["messages"][0] if call["messages"] else None
            if first and first["role"] == "system" and step["agent"] not in found:
                found[step["agent"]] = first["content"]
    return found


def _step_lines(step, prompts, seen):
    """Return the Markdown of one step: new messages, answers in full, then tool calls."""
    parent = f", delegated by step {step['parent']}" if step["parent"] is not None else ""
    lines = [f"## Step {step['index']} ({step['agent']}{parent})"]
    key = (step["agent"], step["parent"])
    for call in step["llm_calls"]:
        lines.append(
            f"### LLM call: {call['model']}, {call['input_tokens']} tokens in, "
            f"{call['output_tokens']} out, cost {call['cost']}"
        )
        users = [item for item in call["messages"] if item["role"] == "user"]
        lines += [f"  user: {item['content']}" for item in users[seen.get(key, 0) :]]
        seen[key] = len(users)
        context = [
            item["content"]
            for item in call["messages"][1:]
            if item["role"] == "system" and item["content"] != prompts.get(step["agent"])
        ]
        lines += [f"  context: {text}" for text in context]
        lines.append(f"  answer: {call['answer']}")
    for tool_call in step["tool_calls"]:
        lines += _tool_lines(tool_call, "### ")
    return lines


def render_markdown(log):
    """Return the export of a run for a report: tokens, prompts, then every step.

    Tokens are by agent, by step and in total, the routing call and nested runs included. Each
    agent's system prompt is printed once; a step shows the messages new to it, its answers in
    full and its tool calls, whose output is cut at ``MESSAGE_CHARACTERS``.
    """
    run = log["run"]
    usage = run["usage"]
    prompts = _prompts(log)
    lines = [
        f"# Run {run['id']}: {run['status']}",
        "",
        f"Loop: {run['loop']}. Started {run['started']}, ended {run['ended']}.",
        "",
        *_token_tables(log),
        "## Prompts",
        "",
    ]
    for agent, text in prompts.items():
        lines += [f"### {agent}", "", text, ""]
    seen = {}
    for step in log["steps"]:
        lines += _step_lines(step, prompts, seen)
    lines.append(
        f"## Totals: {usage['input_tokens']} tokens in, {usage['output_tokens']} out, "
        f"cost {usage['cost']}"
    )
    return "\n".join(lines)


def _command_show(args):
    """Print the log of a stored run."""
    store, run_id = _split_run_folder(args.run)
    print(render_log(runlog(store.load_events(run_id)), args.format == "md"))
    return 0


def _parser():
    """Return the argument parser."""
    parser = argparse.ArgumentParser(prog="geomind", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="answer one message")
    run.add_argument("message")
    run.add_argument("--model")
    run.add_argument("--max-steps", type=int)
    run.add_argument("--mode", choices=["ask", "auto", "readonly", "plan"], default="ask")
    run.add_argument("--sandbox", choices=["local", "docker"])
    run.add_argument("--loop", choices=list(LOOPS))
    run.add_argument("--project")
    run.add_argument("--recording")
    run.add_argument("--record")
    run.set_defaults(function=_command_run)
    chat = commands.add_parser("chat", help="talk to one agent in the terminal")
    chat.add_argument("--agent", default="analyst")
    chat.add_argument("--project")
    chat.add_argument("--live", action="store_true")
    chat.add_argument("--recording")
    chat.add_argument("--model")
    chat.add_argument("--max-steps", type=int)
    chat.set_defaults(function=_command_chat)
    replay = commands.add_parser("replay", help="rerun a stored run offline")
    replay.add_argument("run")
    replay.set_defaults(function=_command_replay)
    show = commands.add_parser("show", help="print the log of a stored run")
    show.add_argument("run")
    show.add_argument("--format", choices=["text", "md"], default="text")
    show.set_defaults(function=_command_show)
    return parser


def main(argv=None):
    """Run one command and return its exit code."""
    args = _parser().parse_args(argv)
    try:
        return args.function(args)
    except GeomindError as error:
        print(f"geomind: {error}", file=sys.stderr)
        return 1
