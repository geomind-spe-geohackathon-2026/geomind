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
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or isinstance(node.value, (bool, str, bytes)):
            continue
        value = node.value
        if isinstance(value, int) and abs(value) <= LITERAL_LIMIT:
            continue
        if isinstance(value, (int, float, complex)):
            found.append(f"line {node.lineno}: {value!r}")
    return found


def _inputs(context, inputs):
    """Return the named inputs resolved to ``{name, reference, value, unit, source}``."""
    if not isinstance(inputs, dict):
        raise _error("inputs is not an object of name: reference", "inputs")
    resolved = []
    for name, reference in inputs.items():
        if not name.isidentifier() or name == "UNITS":
            raise _error(f"inputs name {name!r} is not a Python name (or is UNITS)", "inputs")
        try:
            operand = _operand(context, reference, name)
        except ToolError as error:
            raise _error(str(error).removeprefix("calculate: "), f"inputs.{name}") from error
        resolved.append({"name": name, **operand})
    return resolved


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
    operands = tuple({key: item[key] for key in item if key != "name"} for item in inputs)
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
            written.append({"path": f"{OUTPUT_FOLDER}/{path}", "size": len(data), "text": _cut(text, FILE_CHARACTERS)})
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
    sandbox = getattr(context.session.engine, "sandbox", None)
    if sandbox is None:
        raise _error("this run has no sandbox (the backend's ASSISTANT_SANDBOX)", code="not_allowed")
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
    if not files and not any(
        item["source"]["kind"] in SOURCED_KINDS for item in resolved
    ):
        raise _error(
            f"no input has a source; expected at least one of {', '.join(SOURCED_KINDS)} or a "
            "project file (plain numbers and constants do not count)",
            "inputs",
        )
    content = _project_files(context, files)
    code_id = f"P{uuid4().hex[:8]}"
    try:
        result, written, found = await _run(sandbox, code, resolved, content)
    except SandboxError as error:
        raise _error(str(error), code="unavailable") from error
    status = "ok" if result.exit_code == 0 else "timed_out" if result.exit_code == 124 else "failed"
    calculations = _results(found, code_id, resolved, code) if status == "ok" and found is not None else []
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
