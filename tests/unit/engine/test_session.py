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


class MemoryOfProject(MemoryWorkspace):
    """A workspace that gives the memory of each project, ``None`` where it is off."""

    def __init__(self, memories):
        """Keep ``{project: memory or None}`` and count the calls."""
        super().__init__()
        self.memories = memories
        self.asked = []

    def memory(self, project_id):
        """Return the memory of a project, or ``None`` for the memory off."""
        self.asked.append(project_id)
        return self.memories.get(project_id)


def session_of(workspace, project="p1"):
    """Return a session of a run of ``project`` over ``workspace``."""
    engine = engine_for([says()], workspace=workspace)
    return RunSession(engine, None, RunState(project=project), None)


async def test_the_workspace_memory_is_used_and_needs_no_memory_dir(tmp_path):
    """A workspace that gives the memory is asked once per project; no GEOMIND_MEMORY_DIR."""
    from geomind.stores.memory import MemoryMemory

    given = MemoryMemory()
    workspace = MemoryOfProject({"p1": given})
    session = session_of(workspace)
    with runtime.settings(memory="on", memory_dir=None, memory_similarity=0.8):
        assert session.memory is given and session.memory is given
        assert session.memory_source() == "store"
        assert runtime.memory_problems(session.memory_source()) == []
    assert workspace.asked == ["p1"]
    with runtime.settings(memory="on", memory_dir=None, memory_similarity=None):
        [problem] = runtime.memory_problems("store")
    assert "GEOMIND_MEMORY_SIMILARITY" in problem and "MEMORY_DIR" not in problem


async def test_a_workspace_memory_of_none_turns_the_memory_off_with_no_fallback(tmp_path):
    """``None`` from ``Workspace.memory``: no memory tools, nothing written, no folder store."""
    from geomind.agents import DesignLead
    from geomind.engine import Context
    from geomind.tools import dispatch, write_lesson
    from geomind.types import ToolCall

    session = session_of(MemoryOfProject({}))
    lesson = {"id": "l1", "kind": "lesson", "role": "all", "text": "t", "source": "user"}
    with runtime.settings(memory="on", memory_dir=str(tmp_path), memory_similarity=None):
        assert session.memory is None and session.memory_source() == "off"
        assert runtime.memory_problems("off") == []
        names = [item["name"] for item in session.offered_schemas(DesignLead())]
        asked = ToolCall(id="c1", name="write_lesson", input={"lessons": [lesson]})
        result = await dispatch(write_lesson, asked, Context(project="p1", session=session))
        error = result.output["error"]
    assert "search_memory" not in names and "simulate" in names
    assert error["code"] == "not_allowed"
    assert list(tmp_path.iterdir()) == []


async def test_without_a_workspace_memory_the_folder_store_needs_the_memory_dir(tmp_path):
    """A workspace without ``memory`` (the command line) uses GEOMIND_MEMORY_DIR, else names it."""
    from geomind.stores.memory import FileMemory

    session = session_of(MemoryWorkspace())
    with runtime.settings(memory="on", memory_dir=str(tmp_path), memory_similarity=0.8):
        assert isinstance(session.memory, FileMemory) and session.memory.root == tmp_path
        assert session.memory_source() == "settings"
        assert runtime.memory_problems("settings") == []
    with runtime.settings(memory="on", memory_dir=None, memory_similarity=0.8):
        assert runtime.memory_problems("settings") == [
            "memory: set GEOMIND_MEMORY_DIR or memory_dir"
        ]
        assert "GEOMIND_MEMORY_DIR" in runtime.missing_model_settings()
        with pytest.raises(RunError, match="GEOMIND_MEMORY_DIR"):
            session.memory


async def test_a_live_run_with_a_workspace_memory_is_not_refused_for_the_memory_dir():
    """The settings check of a real provider does not ask for GEOMIND_MEMORY_DIR then."""
    from geomind.stores.memory import MemoryMemory

    session = session_of(MemoryOfProject({"p1": MemoryMemory()}))
    with runtime.settings(memory="on", memory_dir=None, memory_similarity=None):
        problems = runtime.model_problems(session.memory_source())
    assert "memory: set GEOMIND_MEMORY_SIMILARITY or memory_similarity" in problems
    assert not [line for line in problems if "MEMORY_DIR" in line]


def test_model_problems_keeps_its_0_4_22_call_without_a_source():
    """The backend calls ``gd.runtime.model_problems()`` with no argument; it keeps working."""
    from geomind import runtime

    assert runtime.model_problems() == runtime.model_problems("settings")


def test_a_tool_the_user_denied_is_not_asked_again_in_the_request():
    """QA-116: after a denial of build_plant, a later call is refused with the user's reason."""
    from types import SimpleNamespace

    from geomind.engine.session import denied_again, earlier_denial

    events = [
        SimpleNamespace(type="permission", decision="deny", rule="user", tool="build_plant",
                        reason="text only"),
        SimpleNamespace(type="permission", decision="allow", rule="user", tool="simulate",
                        reason=None),
    ]
    assert earlier_denial(events, "build_plant") == "text only"
    assert earlier_denial(events, "simulate") is None
    assert "answer in text" in denied_again("build_plant", "text only")
    assert "answer in text" in denied_again("build_plant", "denied by the user")


def test_a_denial_with_a_change_lets_a_revised_call_be_asked():
    """QA-230: Deny with words asks for a change: a revised set_case is asked, the same is not."""
    from types import SimpleNamespace

    from geomind.engine.session import earlier_denial

    first = {"changes": {"demand": {"return_temperature": {"value": 60, "unit": "degC"}}}}
    revised = {"changes": {"demand": {"return_temperature": {"value": 55, "unit": "degC"}}}}
    events = [
        SimpleNamespace(type="request", call=SimpleNamespace(id="c1", input=first)),
        SimpleNamespace(type="permission", decision="deny", rule="user", tool="set_case",
                        call_id="c1", reason="Change: return temperature 55 instead of 60"),
    ]
    assert earlier_denial(events, "set_case", revised) is None
    reason = "Change: return temperature 55 instead of 60"
    assert earlier_denial(events, "set_case", first) == reason
    plain = [*events[:1], SimpleNamespace(type="permission", decision="deny", rule="user",
                                          tool="set_case", call_id="c1",
                                          reason="denied by the user")]
    assert earlier_denial(plain, "set_case", revised) == "denied by the user"


def test_the_same_denied_write_under_a_new_name_is_refused():
    """QA-288: set_ranges with the same ranges came back as hp_range and hp_capacity_search."""
    from types import SimpleNamespace

    from geomind.engine.session import earlier_denial

    ranges = {"design": "design/v1", "ranges": {"heat_pump.capacity": [3, 15]}}
    first = SimpleNamespace(id="c1", input={**ranges, "name": "a"})
    events = [
        SimpleNamespace(type="request", call=first),
        SimpleNamespace(type="permission", decision="deny", rule="user", tool="set_ranges",
                        call_id="c1", reason="Do not change or search the plant."),
    ]
    reason = "Do not change or search the plant."
    assert earlier_denial(events, "set_ranges", {**ranges, "name": "b"}) == reason
    other = {**ranges, "ranges": {"heat_pump.capacity": [3, 10]}, "name": "b"}
    assert earlier_denial(events, "set_ranges", other) is None


def test_a_set_case_from_the_project_names_its_version_and_changes():
    """QA-224: the card of set_case(source='project') says which version and what changes."""
    from types import SimpleNamespace

    from geomind.engine.session import approval_message, call_summary, project_case_summary

    saved = {"site": {"reservoir": {"permeability": {"value": 150, "unit": "mD"}}}}
    chat = {"site": {"reservoir": {"permeability": {"value": 200, "unit": "mD"}}}}
    workspace = SimpleNamespace(
        case=lambda project: (saved, {}), project_state=lambda project: {"case_version": 4}
    )
    session = SimpleNamespace(
        engine=SimpleNamespace(workspace=workspace),
        state=SimpleNamespace(project="p1", problem=SimpleNamespace(case=chat)),
    )
    text = project_case_summary(session, {"source": "project"})
    assert text == (
        "Load the project's saved case, version 4: "
        "site.reservoir.permeability 200 mD -> 150 mD."
    )
    assert text in approval_message("Allow set_case (write)?", {"source": "project"},
                                     "set_case", text)
    assert call_summary("set_case", {"source": "project"}) == "Load the project's saved case."
    assert project_case_summary(session, {"changes": {}}) is None


def test_a_long_approval_shows_every_value_never_a_cut_json():
    """QA-196: the card cut the JSON at a fixed length and pointed to a log with no pending call."""
    from geomind.engine.session import approval_message

    changes = {"site": {f"layer_{n}": {"value": n, "unit": "m"} for n in range(80)}}
    text = approval_message("Allow set_case (write)?", {"changes": changes}, "set_case")
    assert "changes.site.layer_79: 79 m" in text and "run log" not in text


def test_the_set_case_card_shows_each_economics_value_with_its_unit():
    """QA-168 part 3: the card named only paths, so changed values could not be checked."""
    from geomind.engine.session import call_summary

    economics = {"capex": {"heat_exchanger": {"value": 0.5, "unit": "EUR/(W/K)"}}, "flare": None}
    text = call_summary("set_case", {"economics": economics})
    assert "capex.heat_exchanger: 0.5 EUR/(W/K)" in text and "flare: removed" in text


def test_the_write_lesson_card_lists_every_entry_with_its_text():
    """QA-199: one card for the run's entries, each with its id, role and text."""
    from geomind.engine.session import call_summary

    entry = {"id": "all-a", "kind": "lesson", "role": "all", "text": "Read.", "source": "gemini"}
    text = call_summary("write_lesson", {"lessons": [entry, {**entry, "id": "all-b"}]})
    assert text.startswith("Keep 2 entries") and "all-b (lesson for all, from gemini)" in text


def test_loading_the_saved_case_asks_no_card_and_is_a_no_op_when_it_is_the_chat_s():
    """QA-224: set_case(source='project') loads what the user saved: no approval card."""
    from types import SimpleNamespace

    from geomind.engine.session import SAVED_CASE_LOADED, RunSession
    from geomind.stores import MemoryWorkspace
    from geomind.types import Allow, Deny

    saved = {"name": "c", "economics": "economics.json"}
    files = {"economics.json": b"{}"}
    artifacts = {"case/economics.json": b"{}"}

    def session(case):
        state = SimpleNamespace(project="p", problem=SimpleNamespace(case=case))
        stub = SimpleNamespace(
            engine=SimpleNamespace(workspace=MemoryWorkspace(cases={"p": (saved, files)})),
            state=state,
            load_artifact=artifacts.get,
        )
        stub._same_case_files = lambda found: RunSession._same_case_files(stub, found)
        return stub

    decision, rule = RunSession._saved_case(session(dict(saved)))
    assert isinstance(decision, Deny) and decision.reason == SAVED_CASE_LOADED
    assert rule == "user-saved:same"
    decision, rule = RunSession._saved_case(session({"name": "older"}))
    assert isinstance(decision, Allow) and rule == "user-saved"
    artifacts["case/economics.json"] = b'{"discount_rate": 1}'
    assert isinstance(RunSession._saved_case(session(dict(saved)))[0], Allow)
