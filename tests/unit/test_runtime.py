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


def test_each_role_reads_its_own_model_variable(monkeypatch):
    """``GEOMIND_<ROLE>_MODEL`` sets one role's model; unset means no model, never another's."""
    monkeypatch.setenv("GEOMIND_DESIGNLEAD_MODEL", "x/design")
    monkeypatch.delenv("GEOMIND_CASELEAD_MODEL")
    monkeypatch.setenv("GEOMIND_MODEL", "x/any")
    monkeypatch.setenv("GEOMIND_CHEAP_MODEL", "x/cheap")
    assert runtime.get("designlead_model") == "x/design"
    assert runtime.get("caselead_model") is None
    assert "default_model" not in runtime.state()


def test_every_role_has_its_own_variable():
    """The variable is the role in capitals: ``GEOMIND_CASELEAD_MODEL`` for the case lead."""
    assert runtime.model_variable("caselead") == "GEOMIND_CASELEAD_MODEL"
    assert {f"{role}_model" for role in runtime.ROLES} <= set(runtime.state())


def test_a_stored_state_with_removed_settings_still_loads():
    """A run stored with the sandbox and default model settings resumes without them."""
    stored = {**runtime.state(), "default_model": "x/y", "sandbox_cpu": 1}

    async def load():
        runtime.load_state(stored)
        return "sandbox_cpu" in runtime.state()

    assert asyncio.run(load()) is False


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


def test_missing_model_settings_name_the_environment_variables(monkeypatch):
    """With no role variable set, each role's own variable is named and no role has a model."""
    for role in runtime.ROLES:
        monkeypatch.delenv(runtime.model_variable(role))
    missing = [runtime.model_variable(role) for role in runtime.ROLES]
    assert runtime.missing_model_settings() == missing
    assert set(runtime.role_models().values()) == {None}


async def test_gemini_work_runs_in_a_bounded_pool_when_set():
    """``gemini_threads`` caps the threads gemini work runs in, and they see the settings."""
    import asyncio
    import threading

    from geomind import runtime

    seen = []

    def work():
        seen.append((threading.current_thread().name, runtime.get("max_steps")))
        threading.Event().wait(0.01)

    with runtime.settings(gemini_threads=2, max_steps=7):
        await asyncio.gather(*(runtime.in_gemini_thread(work) for _ in range(8)))
    names = {name for name, _ in seen}
    assert len(names) <= 2 and all(name.startswith("geomind-gemini") for name in names)
    assert {steps for _, steps in seen} == {7}


async def test_unset_gemini_threads_keeps_the_default_executor(monkeypatch):
    """Without the setting gemini work runs where ``asyncio.to_thread`` puts it, as before."""
    import threading

    from geomind import runtime

    monkeypatch.delenv("GEOMIND_GEMINI_THREADS", raising=False)

    name = await runtime.in_gemini_thread(lambda: threading.current_thread().name)
    assert not name.startswith("geomind-gemini")
    assert runtime.get("gemini_threads") is None


async def test_the_result_and_the_error_come_back():
    """A value is returned and an exception raised in the caller, in both modes."""
    from geomind import runtime

    def fails():
        raise ValueError("no")

    for threads in (None, 1):
        with runtime.settings(gemini_threads=threads):
            assert await runtime.in_gemini_thread(divmod, 7, 2) == (3, 1)
            with pytest.raises(ValueError):
                await runtime.in_gemini_thread(fails)


def test_the_retries_of_a_provider_come_from_the_environment(monkeypatch):
    """``GEOMIND_RETRY_COUNT`` and ``GEOMIND_RETRY_DELAY`` set the backoff of a failed call."""
    from geomind import runtime

    monkeypatch.setenv("GEOMIND_RETRY_COUNT", "6")
    monkeypatch.setenv("GEOMIND_RETRY_DELAY", "2.5")
    assert (runtime.get("retry_count"), runtime.get("retry_delay")) == (6, 2.5)
