"""What the fifth live run (0.4.21, CLI) got wrong, replayed offline from its calls.

NOTE: ``tests/fixtures/live/recording_e.jsonl`` is that run's recording, model moves only.
"""

import json
from pathlib import Path

from geomind.stores import MemoryWorkspace
from geomind.tools.gemini.case import set_case
from geomind.tools.gemini.results import search_documents
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

LIVE = Path(__file__).parents[1] / "fixtures" / "live"
RECORDED = [json.loads(line) for line in (LIVE / "recording_e.jsonl").read_text().splitlines()]
FILES = {path.name: path.read_bytes() for path in (LIVE / "files").iterdir()}
BRIEF = "# Brief\n\nThe plant serves a district heating network and a cooling network.\n"


def recorded(index, tool):
    """Return the input of the first call of ``tool`` in completion ``index`` of the recording."""
    return next(item["input"] for item in RECORDED[index]["tool_calls"] if item["name"] == tool)


def session_with(files):
    """Return a session whose project ``p`` holds ``files``."""
    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": files})
    return session


async def test_a_search_without_a_match_says_the_files_do_not_state_it():
    """The run searched 147 times for prices the brief does not give; ``[]`` told it nothing."""
    session = session_with({**FILES, "brief.md": BRIEF.encode()})
    found = (await call(search_documents, recorded(3, "search_documents"), session, "p")).output
    assert found["matches"] == []
    assert "assumption" in found["note"] and "ask_user" in found["note"]


async def test_a_search_made_again_says_so():
    """The same words again: the note says it was searched, with the same matches."""
    session = session_with({"brief.md": BRIEF.encode()})
    query = {"query": "district heating network"}
    first = (await call(search_documents, query, session, "p")).output
    again = await call(search_documents, {"query": "Network heating district"}, session, "p")
    assert (
        again.output["matches"] == first["matches"] and "already searched" in again.output["note"]
    )


async def test_a_file_name_alone_is_no_match():
    """A passage whose words do not match is not found by the name of its file."""
    session = session_with({"heating_demand.csv": b"time,value\n2027-01-01T00:00Z,1\n"})
    found = (await call(search_documents, {"query": "heating demand"}, session, "p")).output
    assert found["matches"] == []


async def test_a_column_named_by_its_old_name_gets_the_new_one():
    """The run renamed ``heating_demand_MWth`` with ``columns`` and then named the old column."""
    output = (await call(set_case, recorded(58, "set_case"), session_with(FILES), "p")).output
    error = output["error"]
    assert error["path"] == "demand.heating.power.column"
    assert any("'heating'" in item and "columns" in item for item in error["suggestions"])
