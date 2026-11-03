"""What the one live run of 0.4.15 got wrong, replayed offline from its recorded calls.

NOTE: ``tests/fixtures/live/recording.jsonl`` is that run's recording (model moves only, no key);
each test takes a call from it as the model made it and checks the answer geomind gives now.
"""

import json
from pathlib import Path

from geomind.stores import MemoryWorkspace
from geomind.tools import read_rag, read_stored
from geomind.tools.gemini.case import case_skeleton, set_case
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

LIVE = Path(__file__).parents[1] / "fixtures" / "live"
RECORDED = [json.loads(line) for line in (LIVE / "recording.jsonl").read_text().splitlines()]
FILES = {path.name: path.read_bytes() for path in (LIVE / "files").iterdir()}


def recorded(index, tool):
    """Return the input of the first call of ``tool`` in completion ``index`` of the recording."""
    return next(item["input"] for item in RECORDED[index]["tool_calls"] if item["name"] == tool)


def session_with_files():
    """Return a session whose project ``p`` holds the run's attached files."""
    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": FILES})
    return session


async def test_a_csv_whose_time_column_has_another_name_gets_the_call_that_fixes_it():
    """The error about a time column of another name carries the exact retry with ``columns``."""
    error = (await call(set_case, recorded(48, "set_case"), session_with_files(), "p")).output
    error = error["error"]
    assert error["code"] == "invalid_value" and "first column" in error["message"]
    retry = error["suggestions"][0]
    assert retry.startswith("set_case(") and "columns=" in retry and "'date': 'time'" in retry


async def test_the_column_mapping_renames_the_header_before_gemini_reads_the_file():
    """With ``columns`` the files are read; whatever gemini says next is not about the column."""
    tool_input = recorded(48, "set_case")
    tool_input["columns"] = {name: {"date": "time"} for name in tool_input["files"]}
    output = (await call(set_case, tool_input, session_with_files(), "p")).output
    assert "first column" not in json.dumps(output)


async def test_a_case_without_its_header_gets_the_skeleton_gemini_s_schema_gives():
    """The recorded call gave files and no case; the gap lists a minimal case to start from."""
    tool_input = recorded(24, "set_case")
    error = (await call(set_case, tool_input, session_with_files(), "p")).output["error"]
    assert error["code"] == "case_incomplete"
    assert json.loads(error["suggestions"][-1]) == case_skeleton()


def test_the_skeleton_holds_every_required_part_of_gemini_s_schema():
    """Made from ``gm.Case.schema()``: its constants as they are, every other leaf named."""
    import gemini as gm

    skeleton = case_skeleton()
    assert set(skeleton) == set(gm.Case.schema()["required"])
    assert skeleton["format"] == 1 and skeleton["kind"] == "case"
    assert skeleton["time"]["step"] == {"value": "<value>", "unit": "<unit>"}


async def test_set_case_names_the_skeleton_in_its_schema():
    """The model sees a minimal case before it tries one."""
    description = set_case.schema()["input_schema"]["properties"]["changes"]["description"]
    assert json.dumps(case_skeleton()) in description


async def test_read_stored_with_a_wrong_path_lists_the_keys_there():
    """The live run asked for ``properties`` and ``text`` 17 times; the keys come back now."""
    session = StubSession()
    await session.save_artifact("result-1", {"name": "x", "table": {"rows": 3}})
    error = (await call(read_stored, {"reference": "result-1", "path": "text"}, session)).output
    assert error["error"]["code"] == "unknown_name"
    assert error["error"]["suggestions"] == ["name", "table"]


async def test_a_page_read_twice_in_one_run_is_a_short_note():
    """The recorded run read the same 7,000 characters of a CSV again and again."""
    session = session_with_files()
    first = recorded(72, "read_document")
    once = (await call(read_rag, first, session, "p")).output
    again = (await call(read_rag, first, session, "p")).output
    assert once["text"] and "text" not in again
    [earlier] = again["already_read"]
    assert (earlier["start"], earlier["end"]) == (0, len(once["text"]))
    assert session.artifacts[earlier["reference"]]["text"] == once["text"]
    forced = (await call(read_rag, {**first, "force": True}, session, "p")).output
    assert "text" not in forced and forced["already_read"] == again["already_read"]
