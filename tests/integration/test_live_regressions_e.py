"""What the fifth live run (0.4.21, CLI) got wrong, replayed offline from its calls.

NOTE: ``tests/fixtures/live/recording_e.jsonl`` is that run's recording, model moves only.
"""

import json
from pathlib import Path

from geomind.stores import MemoryWorkspace
from geomind.tools.gemini.case import set_case
from geomind.tools.gemini.results import rag_search
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
    found = (await call(rag_search, recorded(3, "search_documents"), session, "p")).output
    assert found["matches"] == []
    assert "assumption" in found["note"] and "ask_user" in found["note"]


async def test_a_search_made_again_says_so():
    """The same words again: the note says it was searched, with the same matches."""
    session = session_with({"brief.md": BRIEF.encode()})
    query = {"query": "district heating network"}
    first = (await call(rag_search, query, session, "p")).output
    again = await call(rag_search, {"query": "Network heating district"}, session, "p")
    assert (
        again.output["matches"] == first["matches"] and "already searched" in again.output["note"]
    )


async def test_a_file_name_alone_is_no_match():
    """A passage whose words do not match is not found by the name of its file."""
    session = session_with({"heating_demand.csv": b"time,value\n2027-01-01T00:00Z,1\n"})
    found = (await call(rag_search, {"query": "heating demand"}, session, "p")).output
    assert found["matches"] == []


async def test_a_column_named_by_its_old_name_gets_the_new_one():
    """The run renamed ``heating_demand_MWth`` with ``columns`` and then named the old column."""
    output = (await call(set_case, recorded(58, "set_case"), session_with(FILES), "p")).output
    error = output["error"]
    assert error["path"] == "demand.heating.power.column"
    assert any("'heating'" in item and "columns" in item for item in error["suggestions"])


async def test_a_run_goes_on_live_after_the_replayed_steps():
    """After a fix, the recorded calls before the failure cost nothing and the rest is live."""
    from geomind.providers import FakeLLM, ReplayThenLive
    from tests.fixtures.runs import says

    live = FakeLLM([says("live one"), says("live two")])
    llm = ReplayThenLive(RECORDED[:3], live, steps=2)
    first = await llm.complete([], [], model="m", settings={})
    second = await llm.complete([], [], model="m", settings={})
    third = await llm.complete([], [], model="m", settings={})
    assert first.tool_calls == tuple(
        type(first.tool_calls[0]).model_validate(item) for item in RECORDED[0]["tool_calls"]
    )
    assert first.usage.cost == 0 and second.usage.cost == 0
    assert third.text == "live one" and len(live.calls) == 1


async def test_a_different_tool_result_goes_live_at_that_step(tmp_path):
    """A recorded line whose tool results differ from this run's is not replayed."""
    from geomind.providers import FakeLLM, Recorder, ReplayThenLive
    from geomind.types import Message
    from geomind.utils.json import read_lines
    from tests.fixtures.runs import says

    path = tmp_path / "r.jsonl"
    recorder = Recorder(FakeLLM([says("a"), says("b")]), path)
    said = [Message(role="assistant", content="x"), Message(role="tool", content="old")]
    await recorder.complete([], [], model="m", settings={})
    await recorder.complete(said, [], model="m", settings={})
    live = FakeLLM([says("live")])
    llm = ReplayThenLive(read_lines(path), live, steps=2)
    assert (await llm.complete([], [], model="m", settings={})).text == "a"
    changed = [said[0], Message(role="tool", content="new")]
    assert (await llm.complete(changed, [], model="m", settings={})).text == "live"


def test_replay_needs_its_steps(capsys):
    """``--replay`` without ``--replay-steps`` is refused: there is no default step."""
    from geomind import cli

    assert cli.main(["run", "x", "--replay", "r.jsonl", "--max-cost", "1"]) == 1
    assert "--replay-steps" in capsys.readouterr().err


async def test_a_table_is_not_searched_as_text():
    """Test 6 got rows of the demand CSVs as matches for words of the brief."""
    session = session_with({**FILES, "brief.md": BRIEF.encode()})
    found = (await call(rag_search, {"query": "2027 heating"}, session, "p")).output
    assert [match["name"] for match in found["matches"]] == ["brief.md"]


def test_the_next_round_gets_what_the_last_round_handed_over():
    """Each round of test 6 started from nothing; its task now carries the last round's answer."""
    from geomind.agents.project.drivers import answered_task
    from geomind.engine import Context
    from geomind.types import Message, ToolCall

    handover = "Read the brief; set_case failed on demand.heating.column (older shape)."
    messages = [
        Message(role="user", content="Design it"),
        Message(role="assistant", tool_calls=(ToolCall(id="d1", name="design_lead", input={}),)),
        Message(role="tool", tool_call_id="d1", content=handover),
    ]
    from tests.fixtures.sessions import StubSession

    task = answered_task(Context(messages=messages, session=StubSession()), "use the files")
    assert "use the files" in task and handover in task
