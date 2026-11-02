"""Context-local settings."""

import asyncio

import pytest

from geomind import runtime
from geomind.errors import UnknownNameError


def test_settings_nest_and_restore():
    """A block changes a setting and restores it."""
    before = runtime.get("max_steps")
    with runtime.settings(max_steps=5):
        with runtime.settings(retry_count=0):
            assert (runtime.get("max_steps"), runtime.get("retry_count")) == (5, 0)
    assert runtime.get("max_steps") == before


def test_settings_work_as_decorator():
    """A decorated call sees the change."""

    @runtime.settings(max_steps=2)
    def read():
        return runtime.get("max_steps")

    assert read() == 2


def test_default_model_reads_the_environment(monkeypatch):
    """``GEOMIND_MODEL`` wins over the fixed default."""
    monkeypatch.setenv("GEOMIND_MODEL", "x/y")
    assert runtime.get("default_model") == "x/y"
    monkeypatch.delenv("GEOMIND_MODEL")
    assert runtime.get("default_model") == runtime.FIXED_DEFAULT_MODEL


def test_cheap_model_reads_the_environment(monkeypatch):
    """``GEOMIND_CHEAP_MODEL`` sets the coordinator and the summarizer."""
    monkeypatch.setenv("GEOMIND_CHEAP_MODEL", "x/cheap")
    assert (runtime.get("coordinator_model"), runtime.get("summarizer_model")) == ("x/cheap",) * 2
    monkeypatch.delenv("GEOMIND_CHEAP_MODEL")
    assert runtime.get("coordinator_model") == runtime.FIXED_CHEAP_MODEL


def test_provider_reads_the_environment(monkeypatch):
    """``GEOMIND_PROVIDER`` is a comma-separated list; unset means OpenRouter chooses."""
    monkeypatch.delenv("GEOMIND_PROVIDER", raising=False)
    assert runtime.get("provider") is None
    monkeypatch.setenv("GEOMIND_PROVIDER", " a/fp4, b ,")
    assert runtime.get("provider") == ["a/fp4", "b"]


def test_older_state_loads_without_added_settings():
    """A state stored before ``provider`` existed still loads, with its default."""
    stored = {name: value for name, value in runtime.state().items() if name != "provider"}

    async def load():
        runtime.load_state({**stored, "max_steps": 7})
        return runtime.get("max_steps"), runtime.get("provider")

    assert asyncio.run(load()) == (7, None)


def test_unknown_setting_suggests_a_name():
    """A typo gets a close match."""
    with pytest.raises(UnknownNameError, match="did you mean 'max_steps'"):
        runtime.settings(max_step=1)


def test_state_round_trip_needs_every_name():
    """``load_state`` takes the complete mapping only."""
    with pytest.raises(UnknownNameError, match="every name"):
        runtime.load_state({"max_steps": 1})


async def test_load_state_stays_in_its_task():
    """Loading in a task leaves the caller alone."""

    async def change():
        runtime.load_state({**runtime.state(), "max_steps": 9})
        return runtime.get("max_steps")

    before = runtime.get("max_steps")
    assert await asyncio.create_task(change()) == 9
    assert runtime.get("max_steps") == before
