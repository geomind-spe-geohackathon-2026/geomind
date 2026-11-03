"""What live segment 7 (0.4.22.dev2, run f24ea207) got wrong, replayed offline.

NOTE: the run's recordings are in ``.tmp/live-2026-11-03-g``; these tests rebuild each case.
"""

from geomind.engine import Context
from geomind.loops.design import routed_task_of, should_stop_repeated
from geomind.types import Message, ToolCall
from tests.fixtures.runs import call, run, says, uses

HANDOVER = "Case set; build_plant hc_start stored; site values still missing."


async def test_a_question_on_the_last_step_leaves_a_step_for_its_answer():
    """The designer asked on its last step; after the answer it had no step and ended."""
    script = [uses(call("ask_user", "q1", question="Which site values?")), says("used them")]
    result, engine, _ = await run(script, max_steps=1)
    assert result.status == "waiting"
    resumed = await engine.resume(result.run_id, result.request.id, {"text": "the brief's"})
    assert (resumed.status, resumed.answer) == ("done", "used them")


def test_rounds_without_a_design_are_no_repeated_failure():
    """Two rounds that recorded no design (out of steps) went on to stop at round 2 of 5."""
    history = [["verification_missing"], ["verification_missing"]]
    assert not should_stop_repeated(history, design=None)
    assert should_stop_repeated([["too_cold"], ["too_cold"]], design="design/a")


def test_the_round_after_a_failed_verification_gets_the_handover():
    """Round 2 of segment 7 started from nothing although round 1 had built a plant."""
    messages = [
        Message(role="user", content="Design it"),
        Message(role="assistant", tool_calls=(ToolCall(id="d1", name="designer", input={}),)),
        Message(role="tool", tool_call_id="d1", content=HANDOVER),
    ]
    found = {"failures": [], "passed": False}
    task = routed_task_of(Context(messages=messages), 2, 5, None, None, found)
    assert task.startswith("Round 2 of at most 5") and HANDOVER in task


async def test_a_run_waiting_in_a_nested_run_reports_the_nested_usage():
    """Segment 7 printed 0.033 USD while its calls cost 0.093: the waiting designer was left out."""
    from tests.fixtures.runs import Lead

    script = [
        uses(call("helper", "h1", task="find it")),
        uses(call("ask_user", "q1", question="Which?")),
    ]
    result, _, _ = await run(script, agent=Lead())
    assert result.status == "waiting"
    assert round(result.usage.cost, 6) == 0.02 and result.usage.input_tokens == 20


async def test_an_object_sent_as_a_json_string_says_to_send_the_object():
    """Segment 8 sent ``changes`` and ``plant`` as JSON text three times; the error now says so."""
    from geomind.tools.gemini.plants import build_plant
    from tests.fixtures.calls import call as dispatched

    plant = '{"format": 1, "kind": "plant", "name": "hc", "type": "HeatingCoolingPlant"}'
    error = (await dispatched(build_plant, {"name": "hc", "plant": plant})).output["error"]
    assert error["path"] == "plant"
    assert error["suggestions"] == ["plant is JSON text: send the object itself, not a string"]


def test_a_pdf_table_drawn_word_by_word_reads_as_rows():
    """Segment 9 read a brief whose tables came one word per line and missed their values."""
    from geomind.tools.files import document_text
    from tests.fixtures.pdfs import word_by_word_pdf

    rows = [["Parameter", "Value", "Unit"], ["Pipe length", "120", "m"], ["Pump head", "35", "m"]]
    lines = document_text("table.pdf", word_by_word_pdf(rows)).splitlines()
    assert lines[0] == "[page 1]"
    assert [line.split() for line in lines[1:] if line.strip()] == [
        ["Parameter", "Value", "Unit"],
        ["Pipe", "length", "120", "m"],
        ["Pump", "head", "35", "m"],
    ]


async def test_the_step_limit_waits_and_continue_gives_the_steps_again():
    """A run at its step limit is not lost: it asks, and ``continue`` gives it as many again."""
    from geomind.engine.engine import STEP_OPTIONS

    script = [uses(call("lookup", f"c{index}", key="k")) for index in range(3)] + [says("done")]
    result, engine, _ = await run(script, max_steps=2)
    assert result.status == "waiting" and result.stop_reason == "request"
    assert [option.value for option in result.request.options] == list(STEP_OPTIONS)
    resumed = await engine.resume(result.run_id, result.request.id, {"text": STEP_OPTIONS[0]})
    assert (resumed.status, resumed.answer, resumed.steps) == ("done", "done", 4)


async def test_stop_at_the_step_limit_ends_the_run_as_before():
    """``stop`` ends it with ``step_limit`` and its answer from the record."""
    from geomind.engine.engine import STEP_OPTIONS

    script = [uses(call("lookup", f"c{index}", key="k")) for index in range(3)]
    result, engine, _ = await run(script, max_steps=2)
    resumed = await engine.resume(result.run_id, result.request.id, {"text": STEP_OPTIONS[1]})
    assert (resumed.status, resumed.stop_reason) == ("failed", "step_limit")


def test_max_steps_has_no_default(monkeypatch):
    """Without ``GEOMIND_MAX_STEPS`` the setting is unset and a live run names it as missing."""
    from geomind import runtime

    monkeypatch.delenv("GEOMIND_MAX_STEPS", raising=False)
    assert runtime.get("max_steps") is None
    assert "GEOMIND_MAX_STEPS" in runtime.missing_model_settings()


async def test_a_run_without_max_steps_refuses_to_start(monkeypatch):
    """No step limit at all is refused before any call: the cost needs a bound."""
    import pytest

    from geomind.errors import RunError

    monkeypatch.delenv("GEOMIND_MAX_STEPS", raising=False)
    with pytest.raises(RunError, match="GEOMIND_MAX_STEPS"):
        await run([says("hi")])
