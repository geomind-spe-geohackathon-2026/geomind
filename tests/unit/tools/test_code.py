"""The tools inside the run's sandbox."""

import shutil

import pytest

from swarmax.core import runtime
from swarmax.core.types import ToolCall
from swarmax.tools import dispatch, read_file, run_python, write_file
from tests.fixtures.sessions import StubSession


@pytest.fixture
async def session(tmp_path):
    """Activate a stand-in run with a sandbox."""
    stub = StubSession(tmp_path)
    with runtime.activate(stub):
        yield stub
    if stub.current_sandbox is not None:
        await stub.current_sandbox.close()


def call(**tool_input):
    """Return one call."""
    return ToolCall(id="c1", name="tool", input=tool_input)


async def test_run_python_returns_exit_code_and_output(session):
    """A small calculation runs."""
    result = await dispatch(run_python, call(code="print(6 * 7)"))
    assert result.output["exit_code"] == 0 and result.output["stdout"].strip() == "42"


async def test_run_python_reports_a_failure(session):
    """A failing script is output, not an error of the tool."""
    result = await dispatch(run_python, call(code="raise SystemExit(3)"))
    assert result.output["exit_code"] == 3 and not result.is_error


async def test_files_round_trip(session):
    """What one tool writes the next reads."""
    await dispatch(write_file, call(path="a/b.txt", text="hello"))
    assert (await dispatch(read_file, call(path="a/b.txt"))).output == "hello"


async def test_no_sandbox_configured_is_an_error_result():
    """Without a sandbox the model reads why."""
    with runtime.activate(StubSession()):
        result = await dispatch(run_python, call(code="1"))
    assert result.is_error and "no sandbox is configured" in result.output["error"]["message"]


async def test_lost_sandbox_is_replaced_by_the_next_tool(session):
    """The loss is an error result and the next call provisions a new sandbox."""
    await dispatch(run_python, call(code="1"))
    shutil.rmtree(session.current_sandbox.folder)
    lost = await dispatch(run_python, call(code="1"))
    assert lost.is_error and session.lost == 1
    assert (await dispatch(run_python, call(code="print(1)"))).output["exit_code"] == 0


async def test_large_output_is_cut_with_the_full_text_saved(session):
    """The model gets a cut, the store the whole text."""
    with runtime.settings(tool_result_limit=1000):
        result = await dispatch(run_python, call(code="print('x' * 5000)"))
    stdout = result.output["stdout"]
    assert "[cut;" in stdout and len(stdout) < 1200
    assert len(next(iter(session.artifacts.values()))) > 5000


def test_effects_are_declared():
    """Code tools never count as read tools."""
    assert (run_python.effect, write_file.effect, read_file.effect) == (
        "execute",
        "write",
        "execute",
    )
    assert run_python.idempotent is False
