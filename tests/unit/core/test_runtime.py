"""Context-local settings and the active run."""

import asyncio

import pytest

from swarmax.core import runtime
from swarmax.errors import RunError, UnknownNameError


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
    """``SWARMAX_MODEL`` wins over the fixed default."""
    monkeypatch.setenv("SWARMAX_MODEL", "x/y")
    assert runtime.get("default_model") == "x/y"
    monkeypatch.delenv("SWARMAX_MODEL")
    assert runtime.get("default_model") == runtime.FIXED_DEFAULT_MODEL


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


def test_active_run_outside_a_run_raises():
    """Nothing is active by default."""
    with pytest.raises(RunError, match="no active run"):
        runtime.active_run()


async def test_active_run_reaches_worker_threads():
    """A sync tool in a worker thread sees the run through the copied context."""
    run = object()
    with runtime.activate(run):
        assert await asyncio.to_thread(runtime.active_run) is run
    with pytest.raises(RunError):
        runtime.active_run()
