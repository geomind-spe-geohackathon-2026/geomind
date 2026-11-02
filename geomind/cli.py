"""The command line: run, chat, replay and show."""

import argparse
import asyncio
import hashlib
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from geomind import agents, live, runtime
from geomind.agents import Route
from geomind.context import ProblemState, render
from geomind.engine import Engine, Permissions, callbacks
from geomind.engine.hooks import CostBudget, TokenBudget
from geomind.engine.replay import version_differences
from geomind.errors import GeomindError, RunError
from geomind.export import models_by_agent, render_export
from geomind.providers import FakeLLM, OpenRouter, Recorder
from geomind.run import LOOPS, Run, loop_of
from geomind.sandbox import DockerSandbox, LocalSandbox
from geomind.stores import FileWorkspace
from geomind.stores.casefiles import named_files
from geomind.stores.run import FileRunStore
from geomind.stores.workspace import read_bytes
from geomind.types import Message
from geomind.types.runlog import runlog
from geomind.utils.json import read_json, write_json

RUNS_FOLDER = ".runs"
MESSAGE_CHARACTERS = 2000
ROUTER = "coordinator"


class _Printer(callbacks.Callback):
    """Print text as it streams, and tools as they run."""

    def on_text(self, engine, event):
        """Print a piece of text; the coordinator's route is JSON for the harness, not the user."""
        if event.agent == ROUTER:
            return
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


def _repository(path):
    """Return the commit of the git repository at ``path``, and whether it has changes."""

    def git(*command):
        found = subprocess.run(["git", "-C", str(path), *command], capture_output=True, text=True)
        return found.stdout.strip() if found.returncode == 0 else None

    status = git("status", "--porcelain")
    return {
        "commit": git("rev-parse", "HEAD"),
        "dirty": bool(status) if status is not None else None,
    }


def _sha256(data):
    """Return the hex SHA-256 of bytes."""
    return hashlib.sha256(data).hexdigest()


def _project_files(folder):
    """Return the files of a project a run reads: its case, the files it names and its plants."""
    names = []
    if (folder / "case.json").exists():
        data = read_json(folder / "case.json")
        names = ["case.json", *named_files(data, lambda name: read_bytes(folder / name))]
    return [*names, *(f"plants/{path.name}" for path in sorted((folder / "plants").glob("*.json")))]


def _inputs(args):
    """Return the hashes of what a run reads: the recording and the project's files."""
    paths = {}
    if args.recording is not None:
        paths["recording"] = Path(args.recording)
    if args.project is not None:
        folder = Path(args.project)
        paths.update({f"project/{name}": folder / name for name in _project_files(folder)})
    return {
        key: {"path": str(path), "sha256": _sha256(path.read_bytes())}
        for key, path in paths.items()
    }


def write_manifest(root, run_id, args):
    """Write ``run_manifest.json`` beside a run's log: what reproduces it.

    NOTE: gemini is deterministic and geomind draws no random numbers; every agent runs at
    temperature 0, so the seeds are none and the models and inputs are what matter.
    """
    import gemini as gm

    import geomind

    store = FileRunStore(root)
    events = store.load_events(run_id)
    started = next(
        event for event in events if event.type == "run.started" and event.parent is None
    )
    manifest = {
        "run": {"id": run_id, "loop": started.loop, "arguments": sys.argv[1:]},
        "geomind": {
            "version": geomind.__version__,
            **_repository(Path(geomind.__file__).parents[1]),
        },
        "gemini": {"version": gm.__version__, **_repository(Path(gm.__file__).parents[1])},
        "inputs": _inputs(args),
        "models": models_by_agent(events),
        "settings": started.settings,
        "seeds": {"geomind": None, "gemini": None, "temperature": 0},
    }
    write_json(Path(root) / run_id / "run_manifest.json", manifest)
    return manifest


def _budgets(args):
    """Return the spending caps of ``--max-tokens`` and ``--max-cost``, over the whole run."""
    caps = []
    if args.max_tokens is not None:
        caps.append(TokenBudget(args.max_tokens))
    if args.max_cost is not None:
        caps.append(CostBudget(args.max_cost))
    return caps


def _require_cap(args):
    """Refuse ``--mode auto`` against the real provider without a spending cap."""
    uncapped = args.max_cost is None and args.max_tokens is None
    if args.mode == "auto" and args.recording is None and uncapped:
        raise RunError("run: --mode auto with a live provider needs --max-cost or --max-tokens")


def _command_check_live(args):
    """Print what a live run still lacks; exit 1 when anything is missing."""
    lines, ready = live.report(args.max_cost, args.max_tokens)
    print("\n".join(lines))
    print("ready" if ready else "not ready")
    return 0 if ready else 1


def _command_run(args):
    """Run one message, asking in the terminal when the run pauses.

    Without ``--loop`` the coordinator routes the message; ``--loop`` names the loop instead.
    """
    _require_cap(args)
    workspace, project = _project(args.project)
    _require_case(args, workspace, project)
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
            hooks=_budgets(args),
        )
        if args.loop is not None:
            run.loop = loop_of(Route(kind="loop", loop=args.loop))
        result = run.start()
        while result.status == "waiting":
            result = run.resume(result.request.id, _ask(result.request))
        write_manifest(RUNS_FOLDER, result.run_id, args)
    print(f"\n\nrun {result.run_id}: {result.status} ({result.stop_reason})")
    usage = result.usage
    cached = f" ({usage.cached_tokens} from the cache)" if usage.cached_tokens else ""
    print(f"tokens {usage.input_tokens} in{cached}, {usage.output_tokens} out; cost {usage.cost}")
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


def _require_case(args, workspace, project):
    """Raise unless a design run has a project with a ``case.json``: there is no fallback case."""
    if args.loop != "design":
        return
    if workspace is None or workspace.case(project) is None:
        raise GeomindError(
            f"run: project = {args.project!r}; expected a folder with a case.json for --loop design"
        )


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
        print(render_log(runlog(chat.store.load_events(chat.last_run))))
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


def _difference_text(differences):
    """Return the version differences of a replay as one line."""
    return "; ".join(
        f"{name} recorded {recorded}, now {current}"
        for name, (recorded, current) in differences.items()
    )


def _command_replay(args):
    """Rerun a stored run offline and print pass or the first mismatch."""
    store, run_id = _split_run_folder(args.run)
    workspace, _ = _project(args.project)
    result = asyncio.run(Engine.replay(store, run_id, workspace=workspace))
    print(f"pass: {result.steps} steps, stop reason {result.stop_reason}")
    differences = version_differences(store.load_events(run_id))
    if differences:
        print(f"versions differ: {_difference_text(differences)}")
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


def render_log(log):
    """Return the text of a run log: steps, then totals."""
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


def _read_manifest(folder):
    """Return a run's ``run_manifest.json``, or ``None`` for a run that has none."""
    path = folder / "run_manifest.json"
    return read_json(path) if path.exists() else None


def _command_show(args):
    """Print the log of a stored run."""
    store, run_id = _split_run_folder(args.run)
    events = store.load_events(run_id)
    if args.format == "md":
        print(render_export(events, _read_manifest(Path(args.run))))
        return 0
    print(render_log(runlog(events)))
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
    run.add_argument("--max-tokens", type=int, help="deny model calls once the run used this many")
    run.add_argument("--max-cost", type=float, help="deny model calls once the run cost this, USD")
    run.set_defaults(function=_command_run)
    check = commands.add_parser("check-live", help="check what a first live run needs")
    check.add_argument("--max-tokens", type=int)
    check.add_argument("--max-cost", type=float)
    check.set_defaults(function=_command_check_live)
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
    replay.add_argument("--project", help="the project folder, to replay nested runs that read it")
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
