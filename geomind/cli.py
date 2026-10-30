"""The command line: run, replay and show."""

import argparse
import asyncio
import json
import sys
from pathlib import Path

from geomind import runtime
from geomind.engine import Engine, Permissions, callbacks
from geomind.engine.store import FileRunStore
from geomind.errors import GeomindError
from geomind.providers import OpenRouter
from geomind.run import Run
from geomind.sandbox import DockerSandbox, LocalSandbox
from geomind.types.runlog import runlog

RUNS_FOLDER = ".runs"
MESSAGE_CHARACTERS = 2000


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
        options = f" {list(request.options)}" if request.options else ""
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


def _command_run(args):
    """Run one message, asking in the terminal when the run pauses."""
    with runtime.settings(**_changes(args)):
        run = Run(
            message=args.message,
            llm=OpenRouter(),
            store=FileRunStore(RUNS_FOLDER),
            sandbox=_sandbox(args.sandbox),
            permissions=Permissions(mode=args.mode),
            callbacks=[_Printer()],
        )
        result = run.start()
        while result.status == "waiting":
            result = run.resume(result.request.id, _ask(result.request))
    print(f"\n\nrun {result.run_id}: {result.status} ({result.stop_reason})")
    usage = result.usage
    print(f"tokens {usage.input_tokens} in, {usage.output_tokens} out; cost {usage.cost}")
    return 0 if result.status == "done" else 1


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
    """Return the text of a run log: steps, then totals."""
    step_heading = "## " if is_markdown else ""
    heading = "### " if is_markdown else "- "
    run = log["run"]
    lines = [f"{'# ' if is_markdown else ''}Run {run['id']}: {run['status']}"]
    for step in log["steps"]:
        parent = f", delegated by step {step['parent']}" if step["parent"] is not None else ""
        lines.append(f"{step_heading}Step {step['index']} ({step['agent']}{parent})")
        for llm_call in step["llm_calls"]:
            lines += _llm_lines(llm_call, heading)
        for tool_call in step["tool_calls"]:
            lines += _tool_lines(tool_call, heading)
    usage = run["usage"]
    lines.append(
        f"{step_heading}Totals: {usage['input_tokens']} tokens in, "
        f"{usage['output_tokens']} out, cost {usage['cost']}"
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
    run.set_defaults(function=_command_run)
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
