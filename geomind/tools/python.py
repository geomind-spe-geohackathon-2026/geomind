"""The tool that runs model-written Python in the sandbox, on sourced inputs only.

Numeric inputs come as named references to sourced values, the same as ``calculate``'s operands,
and reach the code as variables; the code holds no data literal (integers up to
``LITERAL_LIMIT`` for indices and counts are allowed). gemini is installed in the sandbox image,
so the code converts units with ``gm.units``. A number the code writes to ``result.json`` becomes
a calculation citing the code and its inputs, which later tools cite by id.

NOTE: the engine's ``sandbox`` (``gd.sandbox.DockerSandbox``) starts one container per call; a run
without one does not offer the tool (``Session.hidden_tools``).
"""

import ast
import json
import math
from typing import Any
from uuid import uuid4

from geomind.context.skills import skill_hint
from geomind.errors import SandboxError, ToolError
from geomind.tools.base import tool
from geomind.tools.calculate import DIMENSIONLESS, SOURCED_KINDS, _operand, new_id
from geomind.utils.json import to_jsonable

LITERAL_LIMIT = 10
"""The largest integer the code may hold as a literal (indices, counts, small exponents)."""
OUTPUT_CHARACTERS = 8000
FILE_CHARACTERS = 20_000
RESULT_FILE = "result.json"
OUTPUT_FOLDER = "out"
HINT = skill_hint("python")
RUNNER = """\
import json
inputs = json.load(open("inputs.json"))
names = {name: item["value"] for name, item in inputs.items()}
names["UNITS"] = {name: item["unit"] for name, item in inputs.items()}
names["__name__"] = "__main__"
exec(compile(open("code.py").read(), "code.py", "exec"), names)
"""


def _error(message, path=None, code="invalid_input"):
    """Return a ``ToolError`` of ``run_python`` that points at its skill."""
    return ToolError(f"run_python: {message}; {HINT}", code=code, path=path)


def literal_problems(code):
    """Return one line per data literal in ``code``; a syntax error is one line too."""
    try:
        tree = ast.parse(code)
    except SyntaxError as error:
        return [f"line {error.lineno}: syntax error: {error.msg}"]
    found = []
    layout = _layout_numbers(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or isinstance(node.value, (bool, str, bytes)):
            continue
        value = node.value
        if isinstance(value, int) and (abs(value) <= LITERAL_LIMIT or id(node) in layout):
            continue
        if isinstance(value, float) and value.is_integer() and abs(value) <= LITERAL_LIMIT:
            continue
        if isinstance(value, (int, float, complex)):
            found.append(f"line {node.lineno}: {value!r}")
    return found


LAYOUT_CALLS = frozenset({"ljust", "rjust", "center", "zfill", "head", "tail", "nlargest"})
"""Methods whose integer argument lays out text or a table, never a value of the problem."""


def _integer(node):
    """Return whether ``node`` is an integer literal, or its negation."""
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.USub):
        node = node.operand
    is_int = isinstance(node, ast.Constant) and isinstance(node.value, int)
    return is_int and not isinstance(node.value, bool)


def _layout_numbers(tree):
    """Return the ids of integer literals that lay out text, never data (QA-296).

    A slice bound or step (``repr(h)[:300]``), the width of ``ljust(20)`` and its kin, and the
    digits of ``round(x, 3)`` were refused as data literals after the user approved the code.
    """
    found = set()

    def add(node):
        if _integer(node):
            found.add(id(node.operand if isinstance(node, ast.UnaryOp) else node))

    for node in ast.walk(tree):
        if isinstance(node, ast.Slice):
            for part in (node.lower, node.upper, node.step):
                add(part)
        elif isinstance(node, ast.Call):
            name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
            if name in LAYOUT_CALLS:
                for argument in node.args:
                    add(argument)
            elif name == "round" and len(node.args) == 2:
                add(node.args[1])
    return found


def _inputs(context, inputs):
    """Return the named inputs resolved to ``{name, reference, value, unit, source}``."""
    if not isinstance(inputs, dict):
        raise _error("inputs is not an object of name: reference", "inputs")
    resolved = []
    for name, reference in inputs.items():
        if not name.isidentifier() or name == "UNITS":
            raise _error(f"inputs name {name!r} is not a Python name (or is UNITS)", "inputs")
        data = _stored_data(context, reference, name)
        if data is not None:
            resolved.append({"name": name, **data})
            continue
        try:
            operand = _operand(context, reference, name)
        except ToolError as error:
            raise _error(str(error).removeprefix("calculate: "), f"inputs.{name}") from error
        resolved.append({"name": name, **operand})
    return resolved


def _stored_data(context, reference, name):
    """Return a stored list or table as one data input, or ``None`` for anything else (QA-205).

    A study's history (``{"stored": "result-...", "path": "history"}``) reaches the code whole, as
    JSON with no unit, its source the stored result: the code reads every trial, not a sample.
    A single stored number goes on as an operand with its unit.
    """
    from geomind.tools.stored import _step, path_keys

    if not isinstance(reference, dict) or set(reference) - {"stored", "path"}:
        return None
    if "stored" not in reference:
        return None
    stored = context.session.load_artifact(reference["stored"])
    if stored is None:
        return None
    part = str(reference.get("path") or "").replace("/", ".").strip(".")
    walked = []
    try:
        for key in path_keys(stored, part):
            stored = _step(stored, key, ".".join(walked))
            walked.append(key)
    except ToolError as error:
        raise _error(str(error).removeprefix("read_stored: "), f"inputs.{name}") from error
    if not isinstance(stored, (list, dict)) or ("value" in stored and "unit" in stored):
        return None
    source = {"kind": "stored", "reference": reference["stored"], "path": part}
    return {"reference": reference, "value": to_jsonable(stored), "unit": None, "source": source}


def _project_files(context, names):
    """Return ``{name: bytes}`` of the project files the code reads."""
    from geomind.tools.files import project_file

    return {name: project_file(context, "run_python", name) for name in names or ()}


def _cut(text, limit=OUTPUT_CHARACTERS):
    """Return text cut to ``limit`` characters, saying so."""
    return text if len(text) <= limit else f"{text[:limit]}\n... ({len(text) - limit} more)"


def _results(found, code_id, inputs, code):
    """Return the calculations of ``result.json``: ``{name: number or {value, unit, label}}``."""
    import gemini as gm

    if not isinstance(found, dict):
        raise _error(f"{RESULT_FILE} is not an object of name: value", RESULT_FILE)
    operands = tuple(
        {
            key: item[key]
            for key in item
            if key != "name" and not (key == "value" and item["unit"] is None)
        }
        for item in inputs
    )
    calculations = []
    for name, item in found.items():
        entry = item if isinstance(item, dict) else {"value": item, "unit": "-"}
        value, unit = entry.get("value"), entry.get("unit") or "-"
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise _error(f"{RESULT_FILE}: {name} is not a number", RESULT_FILE)
        if not math.isfinite(value):
            raise _error(f"{RESULT_FILE}: {name} = {value}, not a finite number", RESULT_FILE)
        if unit not in DIMENSIONLESS and gm.units.si_unit(unit) is None:
            raise _error(f"{RESULT_FILE}: {name} has unit {unit!r}, which gemini does not know")
        calculations.append(
            {
                "id": new_id(),
                "label": str(entry.get("label") or name),
                "operation": "python",
                "expression": f"run_python {code_id}: {name}",
                "value": float(f"{float(value):.12g}"),
                "unit": unit,
                "operands": operands,
                "code": code,
            }
        )
    return calculations


async def _run(sandbox, code, inputs, files):
    """Run the code in a new container; return the result, the output files and result.json."""
    session = await sandbox.provision()
    try:
        values = {item["name"]: {"value": item["value"], "unit": item["unit"]} for item in inputs}
        await session.write("inputs.json", json.dumps(values).encode())
        await session.write("code.py", code.encode())
        await session.write("runner.py", RUNNER.encode())
        await session.write(f"{OUTPUT_FOLDER}/.keep", b"")
        for name, content in files.items():
            await session.write(f"files/{name}", content)
        result = await session.execute(["python3", "runner.py"])
        written = []
        for path in await session.files(OUTPUT_FOLDER):
            if path == ".keep":
                continue
            data = await session.read(f"{OUTPUT_FOLDER}/{path}")
            text = data.decode(errors="replace")
            written.append(
                {
                    "path": f"{OUTPUT_FOLDER}/{path}",
                    "size": len(data),
                    "text": _cut(text, FILE_CHARACTERS),
                }
            )
        try:
            found = json.loads(await session.read(RESULT_FILE))
        except SandboxError:
            found = None
        except json.JSONDecodeError as error:
            raise _error(f"{RESULT_FILE} is not JSON: {error}", RESULT_FILE) from error
        return result, written, found
    finally:
        await session.close()


@tool(effect="execute", idempotent=False)
async def run_python(
    context,
    purpose: str,
    code: str,
    inputs: dict[str, Any] | None = None,
    files: list[str] | None = None,
):
    """Run Python in a sandbox (no network, gemini installed) on sourced inputs. Skill `python`."""
    sandbox, resolved, content = _checked_call(context, purpose, code, inputs, files)
    code_id = f"P{uuid4().hex[:8]}"
    try:
        result, written, found = await _run(sandbox, code, resolved, content)
    except SandboxError as error:
        raise _error(str(error), code="unavailable") from error
    status = "ok" if result.exit_code == 0 else "timed_out" if result.exit_code == 124 else "failed"
    return await _answer(context, purpose, code, files, code_id, resolved, result, written, found,
                         status)


def _checked_call(context, purpose, code, inputs, files):
    """Return ``(sandbox, resolved inputs, files)`` of a call, or raise what refuses it.

    Every check that needs no container: ``run_python.precheck`` runs it before the approval
    card, so the user never approves code the tool then refuses (QA-296).
    """
    sandbox = getattr(context.session.engine, "sandbox", None)
    if sandbox is None:
        raise _error(
            "this run has no sandbox (the backend's ASSISTANT_SANDBOX)", code="not_allowed"
        )
    if not isinstance(purpose, str) or not purpose.strip():
        raise _error("purpose is empty; expected what the code is for", "purpose")
    literals = literal_problems(code)
    if literals:
        raise _error(
            "the code holds data literals; pass each value as a named input instead: "
            + "; ".join(literals[:10]),
            "code",
        )
    resolved = _inputs(context, inputs or {})
    if not files and not any(item["source"]["kind"] in SOURCED_KINDS for item in resolved):
        raise _error(
            f"no input has a source; expected at least one of {', '.join(SOURCED_KINDS)} or a "
            "project file (plain numbers and constants do not count)",
            "inputs",
        )
    return sandbox, resolved, _project_files(context, files)


async def _answer(context, purpose, code, files, code_id, resolved, result, written, found, status):
    """Return the result of a run, keeping the numbers of ``result.json`` as calculations."""
    calculations = (
        _results(found, code_id, resolved, code) if status == "ok" and found is not None else []
    )
    version = None
    if calculations:
        changes = [{"op": "add", "path": "/calculations/-", "value": item} for item in calculations]
        version = await context.session.change_state(changes)
    return {
        "id": code_id,
        "purpose": purpose.strip(),
        "status": status,
        "exit_code": result.exit_code,
        "duration": round(result.duration, 3),
        "code": code,
        "inputs": resolved,
        "files": list(files or ()),
        "stdout": _cut(result.stdout),
        "stderr": _cut(result.stderr),
        "outputs": written,
        "calculations": calculations,
        "version": version,
    }


async def run_python_precheck(context, purpose, code, inputs=None, files=None):
    """Check a ``run_python`` call without running it; raise what the call would refuse."""
    _checked_call(context, purpose, code, inputs, files)


run_python.precheck = run_python_precheck
