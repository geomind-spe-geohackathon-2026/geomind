"""The tools for a module the agent writes: store it, and check it in the sandbox."""

import asyncio
import json
import keyword
from pathlib import Path

from geomind import runtime
from geomind.errors import SandboxError, ToolError
from geomind.sandbox import DockerSandbox, LocalSandbox, Manifest
from geomind.sandbox.base import TIMED_OUT
from geomind.tools.base import tool
from geomind.utils.time import parse_duration

MODULE = "module/"
RUNNER = Path(__file__).parents[2] / "sandbox" / "module_runner.py"
SOURCE = "module.py"
EXAMPLE = "example.json"
REPORT = "report.json"


def check_module_name(name, where):
    """Raise unless ``name`` is a Python identifier that can name a stored module."""
    if not name.isidentifier() or keyword.iskeyword(name):
        raise ToolError(f"{where}: name = {name!r}; expected a Python identifier", path="name")


def sandbox_image():
    """Return the image of this gemini version, pulled by ``make sandbox-image``."""
    import gemini as gm

    return f"gemini-sandbox:{gm.__version__}"


def module_provider(context):
    """Return the sandbox provider that may run agent code: Docker, never the local one."""
    provider = context.session.engine.sandbox
    if provider is None:
        raise SandboxError("test_module: no sandbox is configured for this run")
    if isinstance(provider, LocalSandbox):
        raise ToolError(
            "test_module: the local sandbox is no security boundary and does not run agent code;"
            " run with the docker sandbox",
            code="not_allowed",
        )
    if isinstance(provider, DockerSandbox):
        return DockerSandbox(image=provider.image or sandbox_image())
    return provider


@tool(effect="write")
async def write_module(context, name: str, code: str):
    """Store a gemini module you wrote as the artifact ``module/<name>.py`` and return its name.

    ``name`` is a Python identifier. The code is one file that defines one ``gm.modules.Module``
    subclass; read the skill ``writing-a-gemini-module`` first. Writing again replaces it. Nothing
    runs here: check it with ``test_module``.
    """
    check_module_name(name, "write_module")
    await context.session.save_artifact(f"{MODULE}{name}.py", code)
    return {"module": f"{MODULE}{name}.py", "name": name}


def problems_of(report):
    """Return ``(problems, undecided)`` of gemini's reports, each ``{path, message}``."""
    problems, undecided = [], []
    for item in report["reports"]:
        for check in item["checks"]:
            entry = {"path": f"{item['module']}.{check['name']}", "message": check["message"]}
            if check["passed"] is False:
                problems.append(entry)
            elif check["passed"] is None:
                undecided.append(entry)
    return problems, undecided


def parse_report(name, result):
    """Return the tool result from the runner's output, or raise when it did not report."""
    lines = result.stdout.strip().splitlines()
    try:
        report = json.loads(lines[-1])
    except (IndexError, ValueError) as error:
        raise ToolError(
            f"test_module: name = {name!r}; the check did not report (exit code "
            f"{result.exit_code}): {result.stderr[-1000:]}",
            code="timeout" if result.exit_code == TIMED_OUT else "internal",
        ) from error
    if "error" in report:
        error = report["error"]
        problem = {"path": "import", "message": f"{error['type']}: {error['message']}"}
        return {"name": name, "passed": False, "modules": [], "problems": [problem]}
    problems, undecided = problems_of(report)
    modules = [item["module"] for item in report["reports"]]
    if not modules:
        problems.append({"path": name, "message": "the file defines no gm.modules.Module class"})
    return {
        "name": name,
        "passed": not problems,
        "modules": modules,
        "problems": problems,
        "undecided": undecided,
    }


@tool(effect="execute")
async def test_module(context, name: str, example: dict | None = None):
    """Check a stored module with gemini's module check in the docker sandbox; return its report.

    Runs ``gm.modules.check`` on each module class of ``module/<name>.py`` (see ``write_module``) in
    a container without network, never in this process. Returns ``{name, passed, modules, problems,
    undecided}``: a problem is ``{path, message}`` with the path ``<Class>.<check>`` (``import``
    when the file fails to import), and ``undecided`` lists checks that need values. A module whose
    parameters, controls or inlets have no default needs an ``example`` for the call check, the
    arguments of ``gm.call`` with quantities for values that have a unit:
    ``{"parameters": {...}, "inlets": {...}, "controls": {...}}``.
    """
    check_module_name(name, "test_module")
    code = await asyncio.to_thread(context.session.load_artifact, f"{MODULE}{name}.py")
    if code is None:
        raise ToolError(
            f"test_module: name = {name!r}; expected a module stored with write_module",
            code="unknown_name",
            path="name",
        )
    files = {SOURCE: code, "runner.py": RUNNER.read_text()}
    if example is not None:
        files[EXAMPLE] = json.dumps(example)
    manifest = Manifest.from_runtime().model_copy(update={"files": files, "packages": ()})
    sandbox = await module_provider(context).provision(manifest)
    try:
        timeout = parse_duration(runtime.get("sandbox_timeout"))
        result = await sandbox.execute(["python", "runner.py", SOURCE, EXAMPLE], timeout=timeout)
    finally:
        await sandbox.close()
    return parse_report(name, result)
