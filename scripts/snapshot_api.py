"""Write the snapshots and the JSON schemas of the frozen interfaces.

Usage::

    PYTHONPATH=. python scripts/snapshot_api.py          # after raising gd.__version__
    PYTHONPATH=. python scripts/snapshot_api.py --allow-same-version  # additive, non-breaking

The snapshots go to ``tests/unit/snapshots/`` and the schemas to ``geomind/schemas/``. A snapshot
records the version it belongs to, so a file whose version equals ``gd.__version__`` is not
overwritten without the flag. The rule is in ``.claude/docs/api.md``.
"""

import argparse
import ast
import inspect
import json
import re
import sys
from pathlib import Path

from pydantic import BaseModel, TypeAdapter

import geomind as gd
from geomind import cli
from geomind.agents import Route
from geomind.context import ProblemState
from geomind.engine.callbacks import Callback
from geomind.providers.base import LLM
from geomind.run import AGENTS, LOOPS
from geomind.sandbox.base import Sandbox, SandboxProvider
from geomind.stores import RunStore, UsageLedger, Workspace
from geomind.tools.delegate import DelegateInput
from geomind.types import (
    Answer,
    Completion,
    Message,
    Request,
    RunResult,
    ToolErrorOutput,
    Usage,
)
from geomind.types.events import BASE_FIELDS, EVENT_CLASSES, RequestMade
from geomind.types.patch import StateChange
from geomind.types.results import STATUS_OF_STOP
from geomind.types.runlog import RunLogDocument
from geomind.utils.strings import first_paragraph

ROOT = Path(__file__).resolve().parent.parent
SNAPSHOTS = ROOT / "tests/unit/snapshots"
SCHEMAS = ROOT / "geomind/schemas"
RECORD_KEYS = ("agent", "parent")
SHIPPED_HOOKS = (
    "Hook",
    "TokenBudget",
    "CostBudget",
    "ProjectBudget",
    "RequireApproval",
    "Cancellation",
    "Verified",
)
PROTOCOLS = (RunStore, Workspace, UsageLedger, LLM, Sandbox, SandboxProvider)


def signature_of(function):
    """Return the parameters of a function as text, without annotations."""
    parameters = inspect.signature(inspect.unwrap(function)).parameters.values()
    plain = [parameter.replace(annotation=inspect.Parameter.empty) for parameter in parameters]
    return str(inspect.Signature(plain))


def methods_of(kind):
    """Return ``{method: signature}`` of what a class defines itself."""
    methods = {}
    for name, member in vars(kind).items():
        function = getattr(member, "__func__", member)
        is_public = not name.startswith("_") or name == "__call__"
        is_constructor = name == "__init__" and not getattr(kind, "_is_protocol", False)
        if inspect.isfunction(function) and (is_public or is_constructor):
            methods[name] = signature_of(function)
    return methods


def shape_of(kind):
    """Return the JSON schema of a record, or the methods of a plain class."""
    return kind.model_json_schema() if issubclass(kind, BaseModel) else methods_of(kind)


def tool_entry(item):
    """Return what is frozen of one tool."""
    return {
        "name": item.name,
        "description": item.description.splitlines()[0],
        "effect": item.effect,
        "idempotent": item.idempotent,
        "input_schema": item.input_schema,
        "late_schemas": sorted(item.late_schemas),
    }


def delegate_entry():
    """Return what is frozen of ``Delegate``, whose name is that of its agent."""
    return {
        "name": "Delegate",
        "description": first_paragraph(gd.tools.Delegate.__doc__).splitlines()[0],
        "effect": "compute",
        "idempotent": False,
        "input_schema": DelegateInput.model_json_schema(),
        "late_schemas": [],
    }


def tools_snapshot():
    """Return every tool of the catalogue, by name."""
    namespaces = [gd.tools, gd.tools.gemini]
    tools = [getattr(space, name) for space in namespaces for name in space.__all__]
    entries = {item.name: tool_entry(item) for item in tools if isinstance(item, gd.Tool)}
    return {**entries, "Delegate": delegate_entry()}


def task_model():
    """Return the eval task; ``evals`` is at the repository root, outside the package."""
    if str(ROOT) not in sys.path:
        sys.path.insert(0, str(ROOT))
    from evals.tasks_format import Task

    return Task


def declaration_sections():
    """Return the sections of an agent's constructor, as the structure test fixes them."""
    text = (ROOT / "tests/unit/agents/structure.py").read_text()
    return ast.literal_eval(re.search(r"^SECTIONS = (\[.*\])$", text, re.MULTILINE).group(1))


def command_options(parser):
    """Return ``{option: choices and default}`` of one command."""
    options = {}
    for action in parser._actions:
        if action.dest == "help":
            continue
        flags = action.option_strings or [action.dest]
        if isinstance(action.choices, dict):
            options[flags[0]] = {name: command_options(sub) for name, sub in action.choices.items()}
            continue
        options[flags[0]] = {"choices": action.choices, "default": action.default}
    return options


def commands_snapshot():
    """Return the subcommands of ``geomind``, with their options, and the commands of a chat."""
    commands = next(
        action.choices
        for action in cli._parser()._actions
        if isinstance(getattr(action, "choices", None), dict)
    )
    return {
        "subcommands": {name: command_options(parser) for name, parser in commands.items()},
        "chat": sorted(set(re.findall(r'"(/\w+)"', inspect.getsource(cli._chat_command)))),
    }


def agents_snapshot():
    """Return what the agent developer builds on."""
    return {
        "sections": declaration_sections(),
        "Agent": methods_of(gd.Agent),
        "Prompt": shape_of(gd.Prompt),
        "Model": shape_of(gd.Model),
        "Output": shape_of(gd.Output),
        "Route": Route.model_json_schema(),
        "LOOPS": {name: signature_of(kind.__init__) for name, kind in LOOPS.items()},
        "AGENTS": sorted(AGENTS),
        "eval_task": task_model().model_json_schema(),
        "cli": commands_snapshot(),
    }


def data_keys(kind):
    """Return the keys of an event's ``data()``, beside ``agent`` and ``parent``."""
    if kind is RequestMade:
        return sorted(event_schema(kind)["properties"])
    return sorted(kind.public_fields or set(kind.model_fields) - set(BASE_FIELDS))


def events_snapshot():
    """Return every event type, public or internal, with its class and keys."""
    return {
        name: {"class": kind.__name__, "is_public": kind.is_public, "data": data_keys(kind)}
        for name, kind in EVENT_CLASSES.items()
    }


def api_snapshot():
    """Return what the backend builds on."""
    return {
        "Run": methods_of(gd.Run),
        "RunResult": RunResult.model_json_schema(),
        "stop_reasons": STATUS_OF_STOP,
        "protocols": {kind.__name__: methods_of(kind) for kind in PROTOCOLS},
        "Callback": methods_of(Callback),
        "Permissions": signature_of(gd.Permissions.__init__),
        "hooks": {name: methods_of(getattr(gd.hooks, name)) for name in SHIPPED_HOOKS},
        "Completion": Completion.model_json_schema(),
        "Usage": Usage.model_json_schema(),
        "Message": Message.model_json_schema(),
        "events": events_snapshot(),
        "answers": TypeAdapter(Answer).json_schema(),
        "runlog": RunLogDocument.model_json_schema(),
        "all": sorted(gd.__all__),
    }


def request_data_schema():
    """Return the schema of the ``request`` event, whose JSON flattens the request."""
    schema = Request.model_json_schema()
    properties = dict(schema["properties"])
    properties["request"] = properties.pop("id")
    properties["agent"] = {"type": "string"}
    properties["parent"] = {"anyOf": [{"type": "string"}, {"type": "null"}]}
    required = ["request", "kind", "message", *RECORD_KEYS]
    return schema.get("$defs", {}), properties, required


def event_schema(kind):
    """Return the schema of one public event's ``data()``."""
    if kind is RequestMade:
        definitions, properties, required = request_data_schema()
    else:
        schema = kind.model_json_schema()
        definitions = schema.get("$defs", {})
        names = (*kind.public_fields, *RECORD_KEYS)
        properties = {name: schema["properties"][name] for name in names}
        required = [*(n for n in schema["required"] if n in kind.public_fields), *RECORD_KEYS]
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
        "$defs": definitions,
    }


def events_schema():
    """Return the file of the public events: one schema each, with the definitions at the top."""
    public = {name: kind for name, kind in EVENT_CLASSES.items() if kind.is_public}
    schemas = {name: event_schema(kind) for name, kind in public.items()}
    definitions = {}
    for schema in schemas.values():
        definitions.update(schema.pop("$defs"))
    return {"title": "Public run events", "events": schemas, "$defs": definitions}


def schema_documents():
    """Return ``{file name: schema}`` of the documents exchanged with the backend."""
    return {
        "events.json": events_schema(),
        "problem_state.json": ProblemState.model_json_schema(),
        "state_changed.json": StateChange.model_json_schema(),
        "request.json": Request.model_json_schema(),
        "answer.json": TypeAdapter(Answer).json_schema(),
        "runlog.json": RunLogDocument.model_json_schema(),
        "tool_error.json": ToolErrorOutput.model_json_schema(),
        "eval_task.json": task_model().model_json_schema(),
    }


def render(data):
    """Return the text of one JSON file."""
    return f"{json.dumps(data, indent=2, sort_keys=True, default=list)}\n"


def snapshot_documents():
    """Return ``{file name: snapshot}``, each with the version it belongs to."""
    version = gd.__version__
    return {
        "tools.json": {"version": version, "items": tools_snapshot()},
        "agents.json": {"version": version, "items": agents_snapshot()},
        "api.json": {"version": version, "items": api_snapshot()},
    }


def planned_files(snapshots=SNAPSHOTS, schemas=SCHEMAS):
    """Return ``{path: text}`` of every generated file."""
    files = {snapshots / name: render(data) for name, data in snapshot_documents().items()}
    files.update({schemas / name: render(data) for name, data in schema_documents().items()})
    return files


def recorded_version(path):
    """Return the version a snapshot holds, or ``None`` without one."""
    return json.loads(path.read_text())["version"] if path.exists() else None


def changed_files(files):
    """Return the paths whose text differs from what is on disk."""
    return [path for path, text in files.items() if not path.exists() or path.read_text() != text]


def write_files(files, version_file, *, allow_same_version):
    """Write what changed, or return the message that refuses it; ``None`` when written.

    ``version_file`` is the snapshot whose recorded version decides for all of them, since they are
    written together.
    """
    changed = changed_files(files)
    if changed and not allow_same_version and recorded_version(version_file) == gd.__version__:
        names = ", ".join(path.name for path in changed)
        return (
            f"snapshot: {names} changed at version {gd.__version__}; raise gd.__version__, or "
            "pass --allow-same-version for an additive, non-breaking change"
        )
    for path in changed:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(files[path])
    return None


def main(argv=None):
    """Write the files; return the exit code."""
    parser = argparse.ArgumentParser(description="write the frozen snapshots and schemas")
    parser.add_argument("--allow-same-version", action="store_true")
    args = parser.parse_args(argv)
    refusal = write_files(
        planned_files(), SNAPSHOTS / "api.json", allow_same_version=args.allow_same_version
    )
    if refusal is not None:
        print(refusal, file=sys.stderr)
        return 1
    print(f"snapshots and schemas are at version {gd.__version__}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
