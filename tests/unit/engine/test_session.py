"""The session of a run: models, artifacts and versions."""

import builtins
import platform

import gemini as gm
import httpx
import pytest

import geomind
from geomind import runtime
from geomind.context import compaction
from geomind.engine import Engine, Permissions
from geomind.engine.session import RunSession, current_versions
from geomind.engine.state import RunState, Stop, is_cancel
from geomind.errors import RunError
from geomind.providers import OpenRouter
from geomind.stores import MemoryWorkspace
from geomind.types import Cancel, Deny
from tests.fixtures.runs import (
    Lead,
    Worker,
    call,
    context,
    engine_for,
    of_type,
    run,
    says,
    uses,
)


def test_is_cancel():
    """Only a cancellation ends a run as cancelled."""
    assert is_cancel(Cancel(reason="x")) and not is_cancel(Deny(reason="x"))


def test_stop_defaults():
    """A stop has one reason."""
    assert Stop("answer").request is None


async def test_tools_reach_the_workspace_through_the_session():
    """``context.session.workspace`` is the workspace of the engine."""
    workspace = MemoryWorkspace()
    session = RunSession(engine_for([says()], workspace=workspace), None, RunState(), None)
    assert session.context().session.workspace is workspace


def test_a_session_keeps_artifacts_in_the_space_of_its_chat():
    """A run with a chat saves for the chat; a run without one is the chat of its root run."""
    chat = RunSession(None, None, RunState(chat="c", root="r1"), None)
    plain = RunSession(None, None, RunState(root="r2"), None)
    assert (chat.chat_id, plain.chat_id) == ("c", "r2")


async def test_every_new_run_records_the_versions_it_ran_with():
    """The root run and a nested run log geomind, gemini and python versions."""
    completions = [
        uses(call("helper", task="t")),
        uses(call("lookup", key="x")),
        says("x"),
        says("y"),
    ]
    _, _, events = await run(completions, agent=Lead())
    starts = of_type(events, "run.started")
    assert len(starts) == 2
    expected = {
        "geomind": geomind.__version__,
        "gemini": gm.__version__,
        "python": platform.python_version(),
    }
    assert all(start.versions == expected for start in starts)


def test_a_run_without_gemini_records_no_gemini_key(monkeypatch):
    """No placeholder: an unimportable gemini leaves the key out."""
    real = builtins.__import__

    def refuse(name, *arguments, **options):
        """Fail the import of gemini."""
        if name == "gemini":
            raise ImportError(name)
        return real(name, *arguments, **options)

    monkeypatch.setattr(builtins, "__import__", refuse)
    assert set(current_versions()) == {"geomind", "python"}


def failing_transport():
    """Return a transport that fails the test if a request is made."""
    return httpx.MockTransport(lambda request: pytest.fail("network used"))


async def test_a_real_provider_without_a_model_is_refused_before_any_event():
    """The refusal names every role's missing setting; no event is logged, no request made."""
    engine = Engine(
        llm=OpenRouter(api_key="sk-test", transport=failing_transport()),
        permissions=Permissions(mode="auto"),
    )
    start = context()
    with runtime.settings(designlead_model=None):
        with pytest.raises(RunError, match="designlead: set GEOMIND_DESIGNLEAD_MODEL or designlea"):
            await engine.run(Worker(), start)
    assert engine.store.load_events(start.run_id) == []


async def test_a_scripted_run_never_fetches_the_context_windows(monkeypatch):
    """Fake provider, model set, no window setting: no fetch."""
    monkeypatch.delenv("GEOMIND_CONTEXT_WINDOW")
    monkeypatch.setattr(
        compaction, "fetch_context_windows", lambda: pytest.fail("fetched"), raising=True
    )
    result, _, _ = await run([says("x")])
    assert result.status == "done"


async def test_a_run_with_the_memory_off_is_not_offered_the_memory_tools():
    """#42: with the memory off, agents called search_memory again and again and were refused."""
    from geomind.agents import DesignLead

    session = RunSession(engine_for([says()]), None, RunState(), None)
    with runtime.settings(memory="off"):
        names = [item["name"] for item in session.offered_schemas(DesignLead())]
    assert "search_memory" not in names and "write_memory" not in names
    assert "simulate" in names


async def test_with_the_memory_off_the_curator_is_not_offered_and_a_call_runs_nothing():
    """#127: with the memory off the curator is not offered, and a call of it is not_allowed.

    The support lead had delegated to the curator, which called search_memory and write_lesson
    three times with the memory off.
    """
    from geomind.agents.support.lead import SupportLead

    agent = SupportLead()
    completions = [uses(call("curator", task="keep the lessons")), says("no lessons kept")]
    with runtime.settings(memory="off"):
        session = RunSession(engine_for([says()]), None, RunState(), None)
        names = [item["name"] for item in session.offered_schemas(agent)]
        result, _, events = await run(completions, agent=agent)
    assert "curator" not in names and "summarizer" in names
    assert result.status == "done"
    [answer] = [item for item in of_type(events, "tool.result") if item.tool == "curator"]
    assert answer.is_error and answer.output["error"]["code"] == "not_allowed"
    assert not of_type(events, "run.started")[1:]
