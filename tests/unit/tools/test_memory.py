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
