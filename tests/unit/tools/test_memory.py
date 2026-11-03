"""The memory tools: off by setting, cited writes only, similar designs only."""

from geomind import runtime
from geomind.stores.memory import MemoryMemory
from geomind.tools import read_memory, search_memory, write_memory
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession
from tests.unit.stores.test_memory import CITED


def session_with(memory):
    """Return a session whose memory is ``memory``."""
    session = StubSession()
    session.memory = memory
    return session


async def test_the_tools_say_when_the_memory_is_off():
    """With no memory a search is ``not_allowed``, not a crash."""
    error = (await call(search_memory, {"query": "price"}, session_with(None))).output["error"]
    assert error["code"] == "not_allowed" and "GEOMIND_MEMORY" in error["message"]


async def test_a_cited_value_is_written_and_read_back():
    """``write_memory`` keeps a cited value with the run it came from."""
    memory = MemoryMemory()
    session = session_with(memory)
    assert (await call(write_memory, {"entry": CITED}, session)).output == {"written": "k1"}
    entry = (await call(read_memory, {"section": "knowledge", "id": "k1"}, session)).output
    assert entry["origin_run"] == "r1" and entry["title"] == "A drilling survey"


async def test_an_uncited_value_is_refused():
    """A value without its source never enters the memory."""
    entry = {"id": "k2", "item": "gas price", "value": 0.04, "unit": "EUR/kWh"}
    error = (await call(write_memory, {"entry": entry}, session_with(MemoryMemory()))).output
    assert "title" in error["error"]["message"]


async def test_experience_needs_a_case_and_the_threshold():
    """Without the state's case the experience part is empty, with the reason."""
    session = session_with(MemoryMemory(knowledge=[CITED]))
    with runtime.settings(memory_similarity=0.8):
        found = (await call(search_memory, {"query": "drilling"}, session)).output
    assert found["knowledge"][0]["id"] == "k1" and found["experience"] == []
    assert "case" in found["note"]


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
    found = (await call(search_memory, {"query": "x", "section": "experience"}, session)).output
    assert [item["id"] for item in found["lessons"]] == ["l1"]
    refused = await call(write_lesson, {**lesson, "id": "l2", "text": "use 3 doublets"}, session)
    assert refused.is_error
