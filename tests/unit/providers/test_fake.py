"""The scripted provider."""

import pytest

from swarmax.core.types import RULE_MODEL, Completion
from swarmax.core.types.events import LLMCompleted, StepStarted
from swarmax.errors import ProviderError
from swarmax.providers import FakeLLM
from tests.fixtures import load_completions


async def call(llm, on_text=None):
    """Make one call with empty arguments."""
    return await llm.complete([], [], model="m", settings={}, on_text=on_text)


async def test_script_runs_in_order_and_streams():
    """Each call takes the next completion and its text reaches ``on_text``."""
    llm = FakeLLM([Completion(text="a"), Completion(text="b")])
    seen = []
    assert (await call(llm, seen.append)).text == "a"
    assert (await call(llm, seen.append)).text == "b"
    assert seen == ["a", "b"]


async def test_exhausted_script_raises():
    """A call past the end is a provider failure."""
    with pytest.raises(ProviderError, match="exhausted"):
        await call(FakeLLM([]))


async def test_script_can_fail():
    """An exception in the script is raised."""
    with pytest.raises(ProviderError, match="busy"):
        await call(FakeLLM([ProviderError("busy")]))


async def test_from_events_keeps_only_real_completions():
    """Completions of rule-based steps never called a provider."""
    events = [
        StepStarted(run_id="r", index=1),
        LLMCompleted(run_id="r", index=1, completion=Completion(text="a")),
        LLMCompleted(run_id="r", index=2, completion=Completion(model=RULE_MODEL)),
    ]
    assert (await call(FakeLLM.from_events(events))).text == "a"


async def test_recorded_fixture_loads():
    """Recorded completions come from JSON files."""
    assert "Hello" in (await call(FakeLLM(load_completions("hello")))).text
