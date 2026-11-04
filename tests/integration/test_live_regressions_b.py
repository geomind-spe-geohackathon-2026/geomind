"""What the second live run (0.4.18, run f90f3e12) got wrong, replayed offline from its calls.

NOTE: ``tests/fixtures/live/recording_b.jsonl`` is that run's recording, model moves only.
"""

import json
from pathlib import Path

import pytest

from geomind import live, runtime
from geomind.engine import Engine, Permissions
from geomind.engine.hooks import TokenBudget
from geomind.errors import ProviderError
from geomind.providers import FakeLLM
from geomind.providers.openrouter import _raise_api_error
from geomind.stores import MemoryWorkspace
from geomind.tools import Delegate, dispatch, read_stored
from geomind.tools.gemini.case import set_case
from geomind.tools.gemini.plants import build_plant
from geomind.tools.gemini.skeleton import plant_skeleton
from geomind.types import RunResult, ToolCall
from tests.fixtures.calls import call
from tests.fixtures.runs import Worker, context, says
from tests.fixtures.sessions import StubSession

LIVE = Path(__file__).parents[1] / "fixtures" / "live"
RECORDED = [json.loads(line) for line in (LIVE / "recording_b.jsonl").read_text().splitlines()]
FILES = {path.name: path.read_bytes() for path in (LIVE / "files").iterdir()}
CONTEXT_400 = (
    "This endpoint's maximum context length is 1048576 tokens. However, you requested about "
    "1603930 tokens (1952 of text input, 3720 of tool input, 1598258 in the output)."
)


def recorded(index, tool):
    """Return the input of the first call of ``tool`` in completion ``index`` of the recording."""
    return next(item["input"] for item in RECORDED[index]["tool_calls"] if item["name"] == tool)


def session_with_files():
    """Return a session whose project ``p`` holds the run's attached files."""
    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": FILES})
    return session


class Settings(FakeLLM):
    """Answer from the script and keep the settings of every call."""

    def __init__(self, completions):
        """Keep the script and an empty list of settings."""
        super().__init__(completions)
        self.settings = []

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Keep the settings, then answer."""
        self.settings.append(settings)
        return await super().complete(messages, tools, model=model, settings=settings)


async def test_a_budget_never_asks_for_more_output_than_the_window_leaves():
    """The live run asked for 1,598,258 output tokens: the budget's room, past the window."""
    llm = Settings([says("done")])
    budget = TokenBudget(3_000_000, bound_input=True)
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"), hooks=[budget])
    with runtime.settings(context_window=128_000):
        await engine.run(Worker(), context())
    assert 0 < llm.settings[0]["max_tokens"] < 128_000


def test_a_context_length_refusal_is_context_exceeded():
    """The 400 of OpenRouter for a too long call gets its own code, its numbers kept."""
    with pytest.raises(ProviderError) as raised:
        _raise_api_error({"code": 400, "message": CONTEXT_400})
    assert raised.value.code == "context_exceeded" and "1598258" in str(raised.value)


async def test_a_nested_run_past_the_window_says_so():
    """The delegate answers ``context_exceeded`` with the numbers, not ``internal``."""
    session = StubSession()
    message = f"context_exceeded: OpenRouter: status = 400; {CONTEXT_400}"
    session.result = RunResult(run_id="c", status="failed", stop_reason="error", message=message)
    tool_call = ToolCall(id="c1", name="helper", input={"task": "t"})
    agent = type("Helper", (), {"name": "helper", "__doc__": "Helps."})()
    from geomind.engine import Context

    output = (await dispatch(Delegate(agent), tool_call, Context(session=session))).output
    assert output["error"]["code"] == "context_exceeded" and "1048576" in output["error"]["message"]


async def test_a_series_whose_file_was_not_passed_is_loaded_from_the_project():
    """The run named the CSVs in ``changes`` without ``files=``; they load anyway (#65)."""
    output = (await call(set_case, recorded(27, "set_case"), session_with_files(), "p")).output
    assert "not found" not in json.dumps(output)


async def test_a_wrong_unit_gets_the_accepted_units_and_that_field_corrected():
    """``{"value": "1", "unit": "day"}`` comes back as ``{"value": 1, "unit": "d"}``."""
    tool_input = recorded(22, "set_case")
    error = (await call(set_case, tool_input, session_with_files(), "p")).output["error"]
    assert error["code"] == "invalid_unit"
    assert "time.step = {'value': 1, 'unit': 'd'}" in error["suggestions"]
    accepted = [
        item for item in error["suggestions"] if item.startswith("time.step: accepted units:")
    ]
    assert accepted and " d," in accepted[0]


async def test_requirements_inside_changes_names_the_argument():
    """The suggestion moves them to ``requirements``, by name."""
    error = (await call(set_case, recorded(27, "set_case"), session_with_files(), "p")).output
    if error["error"]["path"] != "changes.requirements":
        tool_input = {"changes": {"requirements": [{"name": "r"}]}}
        error = (await call(set_case, tool_input, session_with_files(), "p")).output
    assert any("requirements={" in item for item in error["error"]["suggestions"])


async def test_a_plant_without_its_header_gets_the_skeleton_gemini_s_schema_gives():
    """The run built ``{"type": ...}`` alone; the error lists a minimal plant file."""
    tool_input = recorded(27, "build_plant")
    output = (await call(build_plant, tool_input, session_with_files(), "p")).output
    assert output["error"]["code"] == "old_format"
    assert json.loads(output["error"]["suggestions"][-1]) == plant_skeleton()
    assert plant_skeleton()["kind"] == "plant"


async def test_read_stored_on_text_says_it_is_text():
    """``path='text'`` on a stored text: the suggestion says to read it whole."""
    session = StubSession()
    await session.save_artifact("result-1", "[page 1]\nsome text")
    error = (await call(read_stored, {"reference": "result-1", "path": "text"}, session)).output
    assert error["error"]["suggestions"] == ["the value is text: read_stored without a path"]


def test_retries_are_required_settings_of_a_live_run(monkeypatch):
    """No built-in retry count or delay: a live run names what is missing."""
    monkeypatch.delenv("GEOMIND_RETRY_COUNT", raising=False)
    monkeypatch.delenv("GEOMIND_RETRY_DELAY", raising=False)
    assert runtime.get("retry_count") is None and runtime.get("retry_delay") is None
    missing = runtime.missing_model_settings()
    assert "GEOMIND_RETRY_COUNT" in missing and "GEOMIND_RETRY_DELAY" in missing
    assert "retries: set GEOMIND_RETRY_COUNT or retry_count" in runtime.model_problems()
    lines = live.missing(max_cost=1.0, fetcher=lambda: set())
    assert "setting not set: GEOMIND_RETRY_DELAY" in lines
