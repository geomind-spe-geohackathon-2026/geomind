"""A paused run resumes in another operating-system process."""

import json
import subprocess
import sys

from tests.fixtures import ROOT

START = """
import sys
import swarmax as sx
from tests.fixtures.runs import call, says, uses
from swarmax.providers import FakeLLM

run = sx.Run(
    message="go",
    llm=FakeLLM([uses(call("ask_user", question="which?"))]),
    store=sx.stores.FileRunStore(sys.argv[1]),
)
result = run.start()
print(run.id, result.request.id)
"""
ANSWER = """
import sys
import json
import swarmax as sx
from tests.fixtures.runs import says
from swarmax.providers import FakeLLM

store = sx.stores.FileRunStore(sys.argv[1])
run = sx.Run.load(sys.argv[2], llm=FakeLLM([says("end")]), store=store)
result = run.resume(sys.argv[3], {"text": "this"})
print(json.dumps([result.status, result.answer]))
"""


def python(code, *arguments):
    """Run code in a new process and return its output."""
    completed = subprocess.run(
        [sys.executable, "-c", code, *arguments],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def test_pause_in_one_process_and_resume_in_another(tmp_path):
    """Nothing but the store connects the two processes."""
    run_id, request_id = python(START, str(tmp_path)).split()
    assert json.loads(python(ANSWER, str(tmp_path), run_id, request_id)) == ["done", "end"]
