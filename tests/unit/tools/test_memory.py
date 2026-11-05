"""The memory tools: off by setting, experience only, similar designs and lessons."""

from geomind import runtime
from geomind.stores.memory import MemoryMemory
from geomind.tools import read_memory, search_memory
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

PAST = {"id": "e1", "features": {"heating_peak": 3e6}, "design": "design/a"}


def session_with(memory):
    """Return a session whose memory is ``memory``."""
    session = StubSession()
    session.memory = memory
    return session


async def test_the_tools_say_when_the_memory_is_off():
    """With no memory a search is ``not_allowed``, not a crash."""
    error = (await call(search_memory, {}, session_with(None))).output["error"]
    assert error["code"] == "not_allowed" and "GEOMIND_MEMORY" in error["message"]


async def test_an_experience_entry_is_read_by_its_id():
    """``read_memory`` returns one past design by the id ``search_memory`` gave."""
    session = session_with(MemoryMemory(experience=[PAST]))
    assert (await call(read_memory, {"id": "e1"}, session)).output["design"] == "design/a"
    assert (await call(read_memory, {"id": "nope"}, session)).is_error


async def test_experience_needs_a_case_and_the_threshold():
    """Without the state's case the past designs are empty, with the reason; lessons still come."""
    session = session_with(MemoryMemory(experience=[PAST]))
    with runtime.settings(memory_similarity=0.8):
        found = (await call(search_memory, {}, session)).output
    assert found["experience"] == [] and "case" in found["note"] and "lessons" in found


async def test_write_lesson_keeps_its_origin_and_search_returns_it_to_the_role():
    """The curator's lesson names its run and source; the role reads it with ``search_memory``."""
    from geomind.stores.memory import MemoryMemory
    from geomind.tools import search_memory, write_lesson
    from tests.fixtures.calls import call
    from tests.fixtures.sessions import StubSession

    session = StubSession()
    session.memory = MemoryMemory()
    lesson = {
        "id": "l1",
        "kind": "lesson",
        "role": "design_lead",
        "text": "review coupled values before sizing",
        "source": "reviewer",
    }
    assert (await call(write_lesson, {"lessons": [lesson]}, session)).output == {"written": ["l1"]}
    entry = session.memory.entries("experience")[0]
    assert entry["origin"] == {"run": "r1", "source": "reviewer"}

    class Lead:
        name = "design_lead"

    session.agent = Lead()
    found = (await call(search_memory, {}, session)).output
    assert [item["id"] for item in found["lessons"]] == ["l1"]
    digit = {**lesson, "id": "l2", "text": "use 3 doublets"}
    refused = await call(write_lesson, {"lessons": [digit]}, session)
    assert refused.is_error


class Named:
    """An agent of a given snake name, for the role the memory tools read."""

    def __init__(self, name):
        """Keep the name."""
        self.name = name


async def test_the_curator_reads_every_role_s_lessons_so_it_writes_none_twice():
    """#95: the curator saw only its own role's lessons and wrote a case lead's lesson again."""
    lesson = {"id": "l1", "kind": "lesson", "role": "case_lead", "text": "send files with changes"}
    entry = {**lesson, "origin": {"run": "seed", "source": "gemini"}}
    session = session_with(MemoryMemory(experience=[entry]))
    session.agent = Named("curator")
    assert [item["id"] for item in (await call(search_memory, {}, session)).output["lessons"]] == [
        "l1"
    ]
    session.agent = Named("design_lead")
    assert (await call(search_memory, {}, session)).output["lessons"] == []


async def test_a_lesson_for_a_role_no_agent_has_is_refused():
    """A lesson for ``designlead`` would reach no agent: the role names one, or ``all``."""
    from geomind.tools import write_lesson

    session = session_with(MemoryMemory())
    lesson = {"id": "l1", "kind": "lesson", "role": "designlead", "text": "check", "source": "user"}
    error = (await call(write_lesson, {"lessons": [lesson]}, session)).output["error"]
    assert error["code"] == "unknown_name" and "designlead" in error["suggestions"]


class BrokenMemory:
    """A backend's memory store that fails on every read and write."""

    def entries(self, section):
        """Fail as a store whose database is gone."""
        raise ConnectionError("memory database unreachable")

    def add(self, section, entry):
        """Fail as a store whose database is gone."""
        raise ConnectionError("memory database unreachable")


async def test_a_failing_memory_store_is_memory_unavailable_never_internal():
    """B4: a store that raises answers ``memory_unavailable`` with its error, never ``internal``."""
    from geomind.tools import write_lesson

    session = session_with(BrokenMemory())
    lesson = {"id": "l1", "kind": "lesson", "role": "all", "text": "t", "source": "user"}
    for tool, arguments in ((search_memory, {}), (read_memory, {"id": "e1"})):
        error = (await call(tool, arguments, session)).output["error"]
        assert error["code"] == "memory_unavailable" and "unreachable" in error["message"]
    error = (await call(write_lesson, {"lessons": [lesson]}, session)).output["error"]
    assert error["code"] == "memory_unavailable"


def test_an_entry_whose_features_are_no_numbers_is_far_never_a_crash():
    """B4: a backend's entry with text or nested features scores as missing, never a TypeError."""
    from geomind.stores.memory import search_experience

    stored = MemoryMemory(
        experience=[
            {"id": "e1", "features": {"heating_peak": "3e6", "depth": 1000.0}},
            {"id": "e2", "features": "not a dict"},
            {"id": "e3", "features": {"heating_peak": 3e6, "depth": True}},
        ]
    )
    found = search_experience(stored, {"heating_peak": 3e6, "depth": 1000.0}, 0.4)
    assert [entry["id"] for entry in found] == ["e1", "e3"]
    assert [entry["similarity"] for entry in found] == [0.5, 0.5]


async def test_search_memory_with_a_workspace_memory_method_is_never_internal():
    """B4, run c8bf2381: 0.4.22 took the bound ``Workspace.memory`` itself as the memory.

    ``memory.entries`` then failed and ``search_memory`` answered ``internal``. The method is
    called for the project, and its memory is searched.
    """
    from geomind.engine import Context
    from geomind.engine.session import RunSession
    from geomind.engine.state import RunState
    from geomind.stores import MemoryWorkspace
    from geomind.tools import dispatch
    from geomind.types import ToolCall
    from tests.fixtures.runs import engine_for, says

    class Backend(MemoryWorkspace):
        """A workspace that gives each project's memory, as the backend does."""

        def memory(self, project_id):
            """Return the project's memory."""
            return MemoryMemory(experience=[PAST])

    session = RunSession(engine_for([says()], workspace=Backend()), None, RunState(), None)
    session.state.project = "p1"
    asked = ToolCall(id="c1", name="read_memory", input={"id": "e1"})
    result = await dispatch(read_memory, asked, Context(project="p1", session=session))
    assert not result.is_error and result.output["design"] == "design/a"


async def test_one_write_lesson_call_keeps_the_run_s_entries_at_most_three():
    """QA-199: nine lessons were nine cards; one call holds them, more than three is refused."""
    from geomind.tools import write_lesson

    session = session_with(MemoryMemory())
    entry = {"kind": "lesson", "role": "all", "text": "read each file once", "source": "gemini"}
    entries = [{**entry, "id": f"all-{name}"} for name in ("a", "b")]
    assert (await call(write_lesson, {"lessons": entries}, session)).output == {
        "written": ["all-a", "all-b"]
    }
    four = [{**entry, "id": f"all-{name}"} for name in ("c", "d", "e", "f")]
    assert (await call(write_lesson, {"lessons": four}, session)).is_error
    assert len(session.memory.entries("experience")) == 2


class Event:
    """A logged event with the fields ``denied_lessons`` reads."""

    def __init__(self, type, **fields):
        """Keep the type and the fields."""
        self.type = type
        self.__dict__.update(fields)


class Call:
    """A pending tool call: its id and input."""

    def __init__(self, id, input):
        """Keep the id and the input."""
        self.id = id
        self.input = input


def denial(call_id, entries, reason="denied by the user"):
    """Return the events of a write_lesson card of ``entries`` the user denied."""
    return [
        Event("request", call=Call(call_id, {"lessons": entries})),
        Event(
            "permission",
            decision="deny",
            rule="user",
            tool="write_lesson",
            call_id=call_id,
            reason=reason,
        ),
    ]


def test_a_denied_lesson_under_another_id_or_role_is_refused_before_its_card():
    """QA-265: a denied lesson came back as role ``all`` under another id, and was asked again."""
    from geomind.tools.memory import repeated_denial

    denied = {
        "id": "case-lead-check-case-accepted-first",
        "kind": "lesson",
        "role": "case_lead",
        "text": "Check the case was accepted before any case step.",
        "source": "support_lead",
    }
    events = denial("c1", [denied], reason="the case lead did not run")
    again = {**denied, "id": "all-check-case-accepted", "role": "all"}
    other = {**denied, "id": "all-read-once", "text": "Read each project document once."}
    assert "all-check-case-accepted" in repeated_denial(events, {"lessons": [again, other]})
    assert repeated_denial(events, {"lessons": [other]}) is None


def test_a_card_of_several_denied_with_words_refuses_only_the_named_entries():
    """A Deny of a card of several entries refuses the ones its words name; the rest may return."""
    from geomind.tools.memory import repeated_denial

    entry = {"kind": "lesson", "role": "all", "source": "gemini"}
    first = {**entry, "id": "all-first", "text": "Read each project document once."}
    second = {**entry, "id": "all-second", "text": "Never re-simulate a stored result."}
    events = denial("c1", [first, second], reason="drop all-second, it is wrong")
    assert repeated_denial(events, {"lessons": [first]}) is None
    assert "all-second" in repeated_denial(events, {"lessons": [first, second]})
