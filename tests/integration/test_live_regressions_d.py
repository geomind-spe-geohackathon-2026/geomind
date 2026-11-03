"""What the fourth live run (0.4.20, CLI) got wrong, replayed offline from its calls.

NOTE: ``tests/fixtures/live/recording_d.jsonl`` is that run's recording, model moves only.
"""

import json
from pathlib import Path

from geomind import cli
from geomind.types import ToolCall
from geomind.utils.json import append_line
from tests.fixtures.runs import ROUTE, says, uses

LIVE = Path(__file__).parents[1] / "fixtures" / "live"
RECORDED = [json.loads(line) for line in (LIVE / "recording_d.jsonl").read_text().splitlines()]
PIPED = (
    "Use what the attached files say; where they give nothing, choose a value, record it as an "
    "assumption with a reason, and go on."
)


def recorded(index, tool):
    """Return the input of the first call of ``tool`` in completion ``index`` of the recording."""
    return next(item["input"] for item in RECORDED[index]["tool_calls"] if item["name"] == tool)


def question_run(tmp_path):
    """Write a recording that asks the run's question with options, then answers; return it."""
    asked = ToolCall(id="q1", name="ask_user", input=recorded(90, "ask_user"))
    path = tmp_path / "recording.jsonl"
    for completion in (ROUTE, uses(asked), says("done")):
        append_line(path, completion.model_dump(mode="json"))
    return str(path)


def typed(monkeypatch, *lines):
    """Answer ``input`` with lines in order, then end of file, as a pipe does."""
    answers = iter(lines)

    def reply(prompt):
        print(prompt)
        try:
            return next(answers)
        except StopIteration:
            raise EOFError from None

    monkeypatch.setattr("builtins.input", reply)


def run(tmp_path, *arguments):
    """Run ``geomind run`` on the recorded question; return the exit code."""
    return cli.main(["run", "Design it", "--recording", question_run(tmp_path), *arguments])


def test_a_free_text_answer_to_options_is_asked_again(tmp_path, monkeypatch, capsys):
    """Test 4 ended with exit 1 on the piped text; now the options are shown and asked again."""
    monkeypatch.chdir(tmp_path)
    typed(monkeypatch, PIPED, "use_proposed")
    assert run(tmp_path, "--answer-retries", "1") == 0
    output = capsys.readouterr().out
    assert "answer with one of: use_proposed, give_values" in output
    assert ": done (" in output


def test_retries_spent_stop_the_run_as_waiting(tmp_path, monkeypatch, capsys):
    """Without ``--answer-retries`` nothing is asked again: the run waits, to be resumed."""
    monkeypatch.chdir(tmp_path)
    typed(monkeypatch, PIPED, PIPED)
    assert run(tmp_path) == cli.WAITING
    captured = capsys.readouterr()
    assert ": waiting (" in captured.out and "q1" not in captured.err
    assert "geomind: answer" not in captured.err


def test_end_of_input_stops_the_run_as_waiting(tmp_path, monkeypatch, capsys):
    """A pipe that ends while a question waits stops the run cleanly, waiting for the answer."""
    monkeypatch.chdir(tmp_path)
    typed(monkeypatch)
    assert run(tmp_path, "--answer-retries", "3") == cli.WAITING
    assert ": waiting (" in capsys.readouterr().out


def test_a_waiting_run_is_resumed_with_the_value_of_an_option(tmp_path, monkeypatch, capsys):
    """``geomind resume`` answers the waiting question in a new process and the run ends."""
    monkeypatch.chdir(tmp_path)
    typed(monkeypatch)
    assert run(tmp_path) == cli.WAITING
    line = next(item for item in capsys.readouterr().out.splitlines() if "geomind resume" in item)
    _, _, run_id, _, request = line.split("resume: ")[1].split()[:5]
    rest = tmp_path / "rest.jsonl"
    append_line(rest, says("done").model_dump(mode="json"))
    arguments = ["--request", request, "--answer", "use_proposed", "--recording", str(rest)]
    assert cli.main(["resume", run_id, *arguments]) == 0
    assert ": done (" in capsys.readouterr().out


async def test_search_documents_finds_the_project_s_attached_files():
    """Test 4 searched the brief for site values six times and got ``[]`` each time."""
    from geomind.stores import MemoryWorkspace
    from geomind.tools.gemini.results import search_rag
    from tests.fixtures.calls import call
    from tests.fixtures.sessions import StubSession

    brief = "# Brief\n\nThe site section: the geothermal gradient and the reservoir temperature.\n"
    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": {"brief.md": brief.encode()}})
    query = recorded(76, "search_documents")
    [found] = (await call(search_rag, query, session, "p")).output["matches"]
    assert found["name"] == "brief.md" and "reservoir" in found["text"]
    assert found["start"] == 0


async def test_a_part_read_from_a_stored_result_is_not_stored_again():
    """``read_stored`` of a long part pointed at a new copy, which the run read again."""
    from geomind.engine import Context
    from geomind.tools import dispatch, read_stored
    from tests.fixtures.sessions import StubSession

    session = StubSession()
    await session.save_artifact("result-1", {"text": "x" * 5000})
    tool_call = ToolCall(id="c9", name="read_stored", input={"reference": "result-1"})
    result = await dispatch(read_stored, tool_call, Context(session=session))
    assert set(session.artifacts) == {"result-1"} and result.reference == "result-1"
