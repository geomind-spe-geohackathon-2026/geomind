"""The script the sandbox runs on an agent's module, run for real in a local subprocess."""

import json
import subprocess
import sys

import pytest

from geomind.sandbox.base import ExecutionResult
from geomind.tools.gemini import modules
from tests.fixtures.modules import BROKEN, EXAMPLE, GOOD


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
