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
    assert (await call(write_lesson, lesson, session)).output == {"written": "l1", "kind": "lesson"}
    entry = session.memory.entries("experience")[0]
    assert entry["origin"] == {"run": "r1", "source": "reviewer"}

    class Lead:
        name = "design_lead"

    session.agent = Lead()
    found = (await call(search_memory, {}, session)).output
    assert [item["id"] for item in found["lessons"]] == ["l1"]
    refused = await call(write_lesson, {**lesson, "id": "l2", "text": "use 3 doublets"}, session)
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
    error = (await call(write_lesson, lesson, session)).output["error"]
    assert error["code"] == "unknown_name" and "designlead" in error["suggestions"]
