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

import httpx

from geomind import agents, live, runtime
from geomind.agents import Route
from geomind.context import ProblemState, render
from geomind.engine import Engine, Permissions, callbacks
from geomind.engine.hooks import CostBudget, ProjectBudget, TokenBudget
from geomind.engine.replay import nested_runs_reused, version_differences
from geomind.errors import GeomindError, RunError
from geomind.export import models_by_agent, render_export
from geomind.providers import FakeLLM, OpenRouter, Recorder, ReplayThenLive
from geomind.run import LOOPS, Run, loop_of
from geomind.stores import FileUsageLedger, FileWorkspace
from geomind.stores.casefiles import named_files
from geomind.stores.run import FileRunStore
from geomind.stores.workspace import read_bytes
from geomind.types import Message, validate_answer
from geomind.types.runlog import runlog
from geomind.utils.envfile import load_env_files
from geomind.utils.json import read_json, write_json
from geomind.utils.models import fetch_prices, load_prices

RUNS_FOLDER = ".runs"
WAITING = 2
"""The exit code of a run that waits for an answer: ``geomind resume`` continues it."""
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


def _answer(request, retries):
    """Return a valid answer typed in the terminal, or ``None`` when there is none.

    An answer the request does not accept, such as free text where options are fixed, is asked
    again with the options shown, at most ``retries`` times (``--answer-retries``; unset, never).
    The end of the input is no answer either, so the run waits and ``geomind resume`` continues it.
    """
    for attempt in range((retries or 0) + 1):
        try:
            answer = _ask(request)
        except EOFError:
            return None
        try:
            return validate_answer(request, answer)
        except GeomindError as error:
            values = ", ".join(option.value for option in request.options or ())
            shown = f"; answer with one of: {values}" if values else ""
            print(f"  geomind: {error}{shown}", flush=True)
    return None


def _until_answered(run, result, retries):
    """Resume ``run`` while it waits and the terminal gives an answer; return the last result."""
    while result.status == "waiting":
        answer = _answer(result.request, retries)
        if answer is None:
            return result
        result = run.resume(result.request.id, answer)
    return result


def _report(result):
    """Print how a run ended and return its exit code: 0 done, ``WAITING`` waiting, else 1."""
    print(f"\n\nrun {result.run_id}: {result.status} ({result.stop_reason})")
    usage = result.usage
    cached = f" ({usage.cached_tokens} from the cache)" if usage.cached_tokens else ""
    print(f"tokens {usage.input_tokens} in{cached}, {usage.output_tokens} out; cost {usage.cost}")
    if result.status == "waiting":
        print(
            f"waiting for: {result.request.message}\n"
            f"resume: geomind resume {result.run_id} --request {result.request.id} --answer ..."
        )
        return WAITING
    return 0 if result.status == "done" else 1


def _changes(args):
    """Return the runtime settings the options change."""
    changes = {}
    if args.model:
        changes.update({f"{role}_model": args.model for role in runtime.ROLES})
    if args.max_steps:
        changes["max_steps"] = args.max_steps
    if getattr(args, "concurrency", None):
        changes["compare_concurrency"] = args.concurrency
    if getattr(args, "retries", None) is not None:
        changes["compare_retries"] = args.retries
    return changes


def _run_provider(args):
    """Return the provider of ``run``: OpenRouter, or a recording; ``--record`` keeps a copy.

    ``--replay FILE --replay-steps N`` answers the first ``N`` calls from a recording and the rest
    live, so a run after a fix goes on from where it failed; both are given or neither.
    """
    replay, steps = getattr(args, "replay", None), getattr(args, "replay_steps", None)
    if (replay is None) != (steps is None):
        raise RunError("run: --replay and --replay-steps go together; expected both or neither")
    if replay is not None and args.recording:
        raise RunError("run: --replay goes on live; expected no --recording with it")
    if args.recording:
        llm = FakeLLM.from_recording(args.recording)
    elif replay is not None:
        llm = ReplayThenLive.from_recording(replay, OpenRouter(), steps)
    else:
        llm = OpenRouter()
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


def _fetch_prices(fetcher=None):
    """Return the prices of the models of the run's roles, or ``None`` and say why.

    A model without a price, or a failed fetch, leaves the cost caps able to refuse a call only
    once reached.
    """
    models = {model for model in live.role_models().values() if model}
    try:
        return asyncio.run(load_prices(models, fetcher or fetch_prices))
    except (httpx.HTTPError, OSError, KeyError, ValueError, GeomindError) as error:
        print(f"prices: not fetched ({type(error).__name__}); cost caps cannot bound a call")
        return None


def _budgets(args, fetcher=None):
    """Return the spending caps of ``--max-tokens`` and ``--max-cost``, over the whole run.

    A live run bounds each call: the prices come from OpenRouter's list. A run from a recording
    costs nothing and fetches none.
    """
    is_live = args.recording is None
    prices = None
    if is_live and (args.max_cost is not None or args.project_max_cost is not None):
        prices = _fetch_prices(fetcher)
    caps = []
    if args.max_tokens is not None:
        caps.append(TokenBudget(args.max_tokens, bound_input=is_live))
    if args.max_cost is not None:
        caps.append(CostBudget(args.max_cost, prices=prices))
    caps.extend(_project_budgets(args, prices, is_live))
    return caps


def _project_budgets(args, prices=None, is_live=False):
    """Return the project cap of ``--project-max-tokens`` and ``--project-max-cost``, if any."""
    if args.project_max_tokens is None and args.project_max_cost is None:
        return []
    if args.project is None:
        raise RunError("run: --project-max-tokens and --project-max-cost need --project")
    ledger = FileUsageLedger(RUNS_FOLDER)
    project = Path(args.project).name
    return [
        ProjectBudget(
            ledger,
            project,
            args.project_max_tokens,
            args.project_max_cost,
            prices=prices,
            bound_input=is_live,
        )
    ]


def _require_cap(args):
    """Refuse ``--mode auto`` against the real provider without a spending cap."""
    uncapped = args.max_cost is None and args.max_tokens is None
    if args.mode == "auto" and args.recording is None and uncapped:
        raise RunError("run: --mode auto with a live provider needs --max-cost or --max-tokens")


def _command_memory_seed(args):
    """Load a cited catalogue (CSV) into the knowledge of the memory the settings name."""
    import csv

    from geomind.stores.memory import FileMemory, catalogue_entries

    if runtime.get("memory") != "on" or runtime.get("memory_dir") is None:
        raise RunError(
            "memory seed: memory = off; expected GEOMIND_MEMORY=on and GEOMIND_MEMORY_DIR"
        )
    path = Path(args.file)
    with path.open(newline="", encoding="utf-8") as file:
        entries = catalogue_entries(list(csv.DictReader(file)), origin=path.name)
    memory = FileMemory(runtime.get("memory_dir"))
    for entry in entries:
        memory.add("knowledge", entry)
    counts = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    shown = ", ".join(f"{count} {status}" for status, count in sorted(counts.items()))
    print(f"seeded {len(entries)} knowledge entries from {path.name}: {shown}")
    return 0


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
    _require_tool_loop(args)
    _require_case(args, workspace, project)
    with runtime.settings(**_changes(args)):
        run = Run(
            message=args.message,
            project=project,
            llm=_run_provider(args),
            store=FileRunStore(RUNS_FOLDER),
            workspace=workspace,
            permissions=Permissions(mode=args.mode),
            callbacks=[_Printer()],
            hooks=_budgets(args),
        )
        if args.loop is not None:
            run.loop = _loop(args)
        result = _until_answered(run, run.start(), args.answer_retries)
        write_manifest(RUNS_FOLDER, result.run_id, args)
    return _report(result)


def _loop(args):
    """Return the loop of ``--loop``; with ``--agent``, the tool loop around that one agent.

    ``--agent`` runs any shipped agent alone, such as ``case_lead``, to try one step of a loop.
    """
    if args.agent is None:
        return loop_of(Route(kind="loop", loop=args.loop))
    return LOOPS["tool"](agents.named(args.agent))


def _require_tool_loop(args):
    """Refuse ``--agent`` with any loop but the tool loop."""
    if args.agent is not None and args.loop != "tool":
        raise RunError(f"run: --agent {args.agent} with --loop {args.loop}; expected --loop tool")


def _command_resume(args):
    """Answer the request a run waits for and continue it, asking in the terminal after that.

    The run is rebuilt from its log in ``.runs``; the provider, the mode and the caps are given
    again, as a new process holds none of them.
    """
    _require_cap(args)
    workspace, _ = _project(args.project)
    with runtime.settings(**_changes(args)):
        run = Run.load(
            args.run,
            llm=_run_provider(args),
            store=FileRunStore(RUNS_FOLDER),
            workspace=workspace,
            permissions=Permissions(mode=args.mode),
            callbacks=[_Printer()],
            hooks=_budgets(args),
        )
        result = run.resume(args.request, {"text": args.answer})
        result = _until_answered(run, result, args.answer_retries)
    return _report(result)


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
    answer_retries: int | None = None


def _chat_provider(args):
    """Return the provider of a chat: OpenRouter, or a recording."""
    if args.live:
        return OpenRouter()
    if args.recording is None:
        raise RunError("chat: expected --live or --recording FILE")
    return FakeLLM.from_recording(args.recording)


def _require_case(args, workspace, project):
    """Raise unless a design run has a project with a ``case.json`` or files that may hold one.

    There is no fallback case; with files the design loop sends the design lead to read them first.
    """
    if args.loop != "design":
        return
    if workspace is not None and workspace.files(project):
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
    result = _until_answered(run, run.start(), chat.answer_retries)
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
    chat.answer_retries = args.answer_retries
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
    events = store.load_events(run_id)
    if nested_runs_reused(events, workspace):
        print("nested runs reused: the run has a project; pass --project to replay them")
    differences = version_differences(events)
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


def _add_project_caps(run):
    """Add the caps over all runs of a project to the ``run`` command."""
    run.add_argument(
        "--project-max-tokens", type=int, help="deny model calls once the project used this many"
    )
    run.add_argument(
        "--project-max-cost", type=float, help="deny model calls once the project cost this, USD"
    )


def _comparison_arguments(run):
    """Add the options of a comparison to the ``run`` command."""
    run.add_argument(
        "--concurrency",
        type=int,
        help="families a comparison designs side by side; unset, one at a time",
    )
    run.add_argument(
        "--retries",
        type=int,
        help="how often a comparison designs a rejected family again; unset, never",
    )


def _run_options(command):
    """Add what ``run`` and ``resume`` both take: the model, the mode, the caps, the answers."""
    command.add_argument("--model")
    command.add_argument("--max-steps", type=int)
    command.add_argument("--mode", choices=["ask", "auto", "readonly", "plan"], default="ask")
    command.add_argument("--project")
    command.add_argument("--recording")
    command.add_argument("--record")
    command.add_argument(
        "--max-tokens", type=int, help="deny model calls once the run used this many"
    )
    command.add_argument(
        "--max-cost", type=float, help="deny model calls once the run cost this, USD"
    )
    _add_project_caps(command)
    _answer_retries(command)
    command.add_argument("--replay", help="a recording whose first calls answer this run")
    command.add_argument(
        "--replay-steps", type=int, help="how many calls of --replay answer before going live"
    )


def _answer_retries(command):
    """Add ``--answer-retries``: how often an answer the request refuses is asked again."""
    command.add_argument(
        "--answer-retries",
        type=int,
        help="ask again this often when an answer is not accepted; unset, never: the run waits",
    )


def _memory_commands(commands):
    """Add ``memory seed FILE``: load a cited catalogue into the memory's knowledge."""
    memory = commands.add_parser("memory", help="manage the agents' memory")
    memory_commands = memory.add_subparsers(dest="memory_command", required=True)
    seed = memory_commands.add_parser("seed", help="load a cited catalogue into the knowledge")
    seed.add_argument("file", help="a CSV with source columns, such as data/knowledge/...")
    seed.set_defaults(function=_command_memory_seed)


def _parser():
    """Return the argument parser."""
    parser = argparse.ArgumentParser(prog="geomind", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="answer one message")
    run.add_argument("message")
    run.add_argument("--loop", choices=list(LOOPS))
    run.add_argument("--agent", help="with --loop tool, the one agent to run, such as case_lead")
    _comparison_arguments(run)
    _run_options(run)
    run.set_defaults(function=_command_run)
    resume = commands.add_parser("resume", help="answer the request a run waits for")
    resume.add_argument("run", help="the run id that `run` printed")
    resume.add_argument("--request", required=True, help="the request id that `run` printed")
    resume.add_argument("--answer", required=True, help="the text, or the value of one option")
    _run_options(resume)
    resume.set_defaults(function=_command_resume)
    _memory_commands(commands)
    check = commands.add_parser("check-live", help="check what a first live run needs")
    check.add_argument("--max-tokens", type=int)
    check.add_argument("--max-cost", type=float)
    check.set_defaults(function=_command_check_live)
    chat = commands.add_parser("chat", help="talk to one agent in the terminal")
    chat.add_argument("--agent", default="analysis_lead")
    chat.add_argument("--project")
    chat.add_argument("--live", action="store_true")
    chat.add_argument("--recording")
    chat.add_argument("--model")
    chat.add_argument("--max-steps", type=int)
    _answer_retries(chat)
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


def real_env_files():
    """Return the ``.env`` files a command reads: the repository's, then the user's ``live.env``.

    The repository is the nearest folder above the working folder that holds ``.git``.
    """
    here = Path.cwd()
    repository = next(
        (folder for folder in (here, *here.parents) if (folder / ".git").exists()), None
    )
    files = [repository / ".env"] if repository is not None else []
    return [*files, Path.home() / ".config" / "geomind" / "live.env"]


env_files = real_env_files


def main(argv=None):
    """Run one command and return its exit code, the settings of ``env_files`` read first."""
    args = _parser().parse_args(argv)
    load_env_files(env_files())
    try:
        return args.function(args)
    except GeomindError as error:
        print(f"geomind: {error}", file=sys.stderr)
        return 1
