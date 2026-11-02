"""Every numbered example runs offline as a script."""

import os
import re
import subprocess
import sys

import pytest

from tests.fixtures import ROOT

EXAMPLES = sorted(
    path.relative_to(ROOT).as_posix()
    for path in (ROOT / "examples").rglob("*.py")
    if re.match(r"\d\d_", path.name)
)
EXPECTED = {
    "01_hello.py": "Hello!",
    "02_custom_agent.py": "42",
    "03_approval.py": "The report is sent.",
    "04_sandbox.py": "5050",
    "05_case.py": "unmet requirements: 0",
    "01_queue_and_resume.py": "event: request",
}


@pytest.mark.parametrize("path", EXAMPLES)
def test_example_runs(path, tmp_path):
    """The script exits cleanly and prints what it shows."""
    environment = {key: value for key, value in os.environ.items() if key != "OPENROUTER_API_KEY"}
    environment["PYTHONPATH"] = str(ROOT)
    completed = subprocess.run(
        [sys.executable, str(ROOT / path)],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=120,
    )
    assert completed.returncode == 0, completed.stderr
    assert EXPECTED[path.rpartition("/")[2]] in completed.stdout
