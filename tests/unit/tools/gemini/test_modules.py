"""write_module and test_module, with a fake sandbox and the runner run for real once."""

import json
import subprocess
import sys

import pytest

from geomind.engine import Context
from geomind.sandbox import DockerSandbox, LocalSandbox
from geomind.sandbox.base import ExecutionResult
from geomind.tools import dispatch
from geomind.tools.gemini import modules, test_module, write_module
from geomind.types import ToolCall
from tests.fixtures.modules import BROKEN, EXAMPLE, GOOD
from tests.fixtures.sessions import StubSession


class FakeSandbox:
    """Answers the runner with a canned output and keeps what went in."""

    def __init__(self, output, exit_code=0):
        """Keep the canned answer."""
        self.output = output
        self.exit_code = exit_code
        self.manifest = None
        self.closed = False
        self.commands = []

    async def provision(self, manifest):
        """Remember the manifest and act as the sandbox."""
        self.manifest = manifest
        return self

    async def execute(self, command, *, timeout):
        """Record the command and return the canned result."""
        self.commands.append(command)
        return ExecutionResult(exit_code=self.exit_code, stdout=self.output)

    async def close(self):
        """Remember the close."""
        self.closed = True


class Engine:
    """Holds the provider of the run."""

    def __init__(self, sandbox):
        """Keep the provider."""
        self.sandbox = sandbox


def session_with(provider):
    """Return a stand-in run whose engine has ``provider``."""
    session = StubSession()
    session.engine = Engine(provider)
    return session


async def run_tool(tool, session, **tool_input):
    """Dispatch one call and return the result."""
    call = ToolCall(id="c1", name=tool.name, input=tool_input)
    return await dispatch(tool, call, Context(session=session))


def report(*checks, module="Heater"):
    """Return the runner's output for one class with ``(name, passed, message)`` checks."""
    items = [{"name": n, "passed": p, "message": m} for n, p, m in checks]
    return json.dumps({"reports": [{"module": module, "passed": True, "checks": items}]})


async def test_write_module_stores_the_file_as_an_artifact():
    """The code is kept under ``module/<name>.py``."""
    session = StubSession()
    result = await run_tool(write_module, session, name="heater", code=GOOD)
    assert result.output == {"module": "module/heater.py", "name": "heater"}
    assert session.artifacts["module/heater.py"] == GOOD


@pytest.mark.parametrize("name", ["a b", "../x", "1x", "class", "x.py", ""])
async def test_a_name_must_be_an_identifier(name):
    """Anything else is refused, and nothing is stored."""
    session = StubSession()
    result = await run_tool(write_module, session, name=name, code="x")
    assert result.is_error and result.output["error"]["path"] == "name"
    assert session.artifacts == {}


async def test_an_unknown_module_is_unknown_name():
    """Only a stored module is tested."""
    result = await run_tool(test_module, session_with(FakeSandbox("")), name="missing")
    assert result.output["error"]["code"] == "unknown_name"


async def test_the_report_lists_problems_and_undecided_checks():
    """A failed check is a problem with its path and message; ``None`` is undecided."""
    fake = FakeSandbox(
        report(("category", False, "category = 'x'"), ("call", None, "needs example"))
    )
    session = session_with(fake)
    session.artifacts["module/heater.py"] = GOOD
    result = await run_tool(test_module, session, name="heater", example=EXAMPLE)
    assert result.output == {
        "name": "heater",
        "passed": False,
        "modules": ["Heater"],
        "problems": [{"path": "Heater.category", "message": "category = 'x'"}],
        "undecided": [{"path": "Heater.call", "message": "needs example"}],
    }


async def test_a_passing_module_and_what_goes_into_the_sandbox():
    """The code, the runner and the example go in; no package is mounted; the box is closed."""
    fake = FakeSandbox(report(("call", True, "ok")))
    session = session_with(fake)
    session.artifacts["module/heater.py"] = GOOD
    result = await run_tool(test_module, session, name="heater", example=EXAMPLE)
    assert result.output["passed"] is True
    files = fake.manifest.files
    assert files["module.py"] == GOOD and json.loads(files["example.json"]) == EXAMPLE
    assert "gm.modules.check" in files["runner.py"]
    assert fake.manifest.packages == () and fake.manifest.network is False
    assert fake.closed and fake.commands == [["python", "runner.py", "module.py", "example.json"]]


async def test_an_import_error_is_a_problem():
    """The runner reports a file that fails to import."""
    fake = FakeSandbox(json.dumps({"error": {"type": "SyntaxError", "message": "bad"}}))
    session = session_with(fake)
    session.artifacts["module/heater.py"] = "x ="
    result = await run_tool(test_module, session, name="heater")
    assert result.output["problems"] == [{"path": "import", "message": "SyntaxError: bad"}]


async def test_a_file_without_a_module_class_fails():
    """Nothing to check is no pass."""
    fake = FakeSandbox(json.dumps({"reports": []}))
    session = session_with(fake)
    session.artifacts["module/heater.py"] = "x = 1"
    result = await run_tool(test_module, session, name="heater")
    assert result.output["passed"] is False and "no gm.modules.Module" in str(result.output)


async def test_a_crashed_check_is_an_error_result():
    """No report is an error that carries the exit code."""
    session = session_with(FakeSandbox("", exit_code=1))
    session.artifacts["module/heater.py"] = GOOD
    result = await run_tool(test_module, session, name="heater")
    assert result.is_error and "did not report" in result.output["error"]["message"]


async def test_the_local_sandbox_is_refused_for_agent_code(tmp_path):
    """Agent code never runs in the local sandbox."""
    session = session_with(LocalSandbox(tmp_path))
    session.artifacts["module/heater.py"] = GOOD
    result = await run_tool(test_module, session, name="heater")
    assert result.output["error"]["code"] == "not_allowed"
    assert not list(tmp_path.iterdir())


async def test_no_sandbox_is_a_sandbox_error():
    """A run without a sandbox cannot test."""
    session = session_with(None)
    session.artifacts["module/heater.py"] = GOOD
    result = await run_tool(test_module, session, name="heater")
    assert result.is_error and "no sandbox" in result.output["error"]["message"]


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def test_docker_gets_the_image_of_this_gemini_version(gm):
    """The provider is a Docker sandbox on ``gemini-sandbox:<version>``, unless one was chosen."""
    chosen = session_with(DockerSandbox())
    assert (
        modules.module_provider(Context(session=chosen)).image == f"gemini-sandbox:{gm.__version__}"
    )
    own = session_with(DockerSandbox(image="mine"))
    assert modules.module_provider(Context(session=own)).image == "mine"


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    """Return the real runner's report on the correct, the broken and a syntax-error file."""
    folder = tmp_path_factory.mktemp("runner")
    (folder / "example.json").write_text(json.dumps(EXAMPLE))
    outputs = {}
    for name, code in (("good", GOOD), ("broken", BROKEN), ("syntax", "x =")):
        (folder / f"{name}.py").write_text(code)
        done = subprocess.run(
            [sys.executable, str(modules.RUNNER), f"{name}.py", "example.json"],
            cwd=folder,
            capture_output=True,
            text=True,
        )
        outputs[name] = modules.parse_report(name, ExecutionResult(exit_code=0, stdout=done.stdout))
    return outputs


def test_the_runner_passes_a_correct_module(runs):
    """The check of gemini passes it with the example."""
    assert runs["good"]["passed"] is True and runs["good"]["modules"] == ["ResistanceHeater"]


def test_the_runner_reports_a_broken_module(runs):
    """The failed checks come back with their paths."""
    paths = {item["path"] for item in runs["broken"]["problems"]}
    assert {"Wrong.units", "Wrong.forward_signature"} <= paths


def test_the_runner_reports_a_syntax_error(runs):
    """The import fails as a problem."""
    assert runs["syntax"]["problems"][0]["path"] == "import"
