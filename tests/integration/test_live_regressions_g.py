"""What live segment 7 (0.4.22.dev2, run f24ea207) got wrong, replayed offline.

NOTE: the run's recordings are in ``.tmp/live-2026-11-03-g``; these tests rebuild each case.
"""

from geomind.agents.project.drivers import routed_task_of, should_stop_repeated
from geomind.engine import Context
from geomind.types import Message, ToolCall
from tests.fixtures.runs import call, run, says, uses

HANDOVER = "Case set; build_plant hc_start stored; site values still missing."


async def test_a_question_on_the_last_step_leaves_a_step_for_its_answer():
    """The design lead asked on its last step; after the answer it had no step and ended."""
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
        Message(role="assistant", tool_calls=(ToolCall(id="d1", name="design_lead", input={}),)),
        Message(role="tool", tool_call_id="d1", content=HANDOVER),
    ]
    found = {"failures": [], "passed": False}
    task = routed_task_of(Context(messages=messages), 2, 5, None, None, found)
    assert task.startswith("Round 2 of at most 5") and HANDOVER in task


async def test_a_run_waiting_in_a_nested_run_reports_the_nested_usage():
    """Segment 7 printed 0.033 USD while its calls cost 0.093: the waiting lead was left out."""
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


async def test_a_document_read_stays_whole_in_the_history():
    """The case lead re-read a 3.6k brief 16 times: its page left the history after one step."""
    from geomind.engine import Context
    from geomind.stores import MemoryWorkspace
    from geomind.tools import dispatch, read_rag, read_stored
    from tests.fixtures.sessions import StubSession

    session = StubSession()
    session.workspace = MemoryWorkspace(files={"p": {"brief.md": ("word " * 1000).encode()}})
    page = ToolCall(id="r1", name="read_rag", input={"name": "brief.md"})
    result = await dispatch(read_rag, page, Context(project="p", session=session))
    assert result.reference is not None and len(result.output["text"]) == 5000
    await session.save_artifact("result-9", {"text": "x" * 5000})
    part = ToolCall(id="r2", name="read_stored", input={"reference": "result-9"})
    assert (await dispatch(read_stored, part, Context(session=session))).reference == "result-9"


async def test_a_part_too_long_to_show_names_the_deeper_paths():
    """The case lead read the schema's ``properties`` 7 times; now the part names its keys."""
    from geomind import runtime
    from geomind.tools import read_stored
    from tests.fixtures.calls import call as dispatched
    from tests.fixtures.sessions import StubSession

    session = StubSession()
    big = {"properties": {"site": {"x": "y" * 3000}, "demand": {"z": "w" * 3000}}}
    await session.save_artifact("result-9", big)
    with runtime.settings(tool_result_limit=1500):
        tool_input = {"reference": "result-9", "path": "properties"}
        output = (await dispatched(read_stored, tool_input, session)).output
    assert output["keys"] == ["site", "demand"]
    assert "path='properties.site'" in output["note"]


async def test_a_path_with_slashes_reads_as_dots():
    """``properties/site`` is read as ``properties.site``."""
    from geomind.tools import read_stored
    from tests.fixtures.calls import call as dispatched
    from tests.fixtures.sessions import StubSession

    session = StubSession()
    await session.save_artifact("result-9", {"properties": {"site": {"a": 1}}})
    tool_input = {"reference": "result-9", "path": "properties/site"}
    assert (await dispatched(read_stored, tool_input, session)).output == {"a": 1}


def test_a_kept_result_stays_whole_for_the_kept_turns_then_shrinks():
    """A document page stays whole while it is recent, then shrinks to its outline, stored."""
    from geomind import runtime
    from geomind.engine import Context
    from tests.fixtures.runs import Worker

    page = ToolCall(id="r1", name="read_rag", input={"name": "brief.md"})
    messages = [
        Message(role="user", content="go"),
        Message(role="assistant", tool_calls=(page,)),
        Message(role="tool", tool_call_id="r1", content="the whole page"),
    ]

    class Reader(Worker):
        """A worker that also reads documents."""

        def __init__(self):
            """Add the document tool."""
            super().__init__()
            self.read_rag = read_rag

    from geomind.tools import read_rag

    agent = Reader()
    context = Context(messages=list(messages), stored={"r1": "outline of the page"})

    def shown():
        history = context.messages_for(agent)
        return next(item.content for item in history if item.tool_call_id == "r1")

    with runtime.settings(compaction_keep_turns=2):
        context.messages.append(Message(role="assistant", content="step 2"))
        assert shown() == "the whole page"
        context.messages.append(Message(role="assistant", content="step 3"))
        context.messages.append(Message(role="assistant", content="step 4"))
        assert shown() == "outline of the page"


async def test_one_call_s_output_is_bounded_by_its_setting():
    """One runaway completion wrote 103,404 tokens: the per-call output limit bounds every call."""
    from geomind import runtime
    from geomind.engine import Engine, Permissions
    from geomind.engine.hooks import TokenBudget
    from tests.fixtures.runs import Worker, context
    from tests.integration.test_live_regressions_b import Settings

    llm = Settings([says("done")])
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"), hooks=[TokenBudget(10**7)])
    with runtime.settings(max_output_tokens=4000):
        await engine.run(Worker(), context())
    assert llm.settings[0]["max_tokens"] == 4000


def test_the_output_limit_is_a_required_live_setting(monkeypatch):
    """No built-in limit: a live run names GEOMIND_MAX_OUTPUT_TOKENS when it is unset."""
    from geomind import runtime

    monkeypatch.delenv("GEOMIND_MAX_OUTPUT_TOKENS", raising=False)
    assert runtime.get("max_output_tokens") is None
    assert "GEOMIND_MAX_OUTPUT_TOKENS" in runtime.missing_model_settings()


async def test_a_completion_cut_at_the_limit_is_retried_with_a_note():
    """A call that stops at the output limit is no answer: the model is told and asked again."""
    from geomind.types import Completion
    from tests.fixtures.runs import USAGE

    cut = Completion(text="", usage=USAGE, model="fake/model", raw={"finish_reason": "length"})
    result, _, events = await run([cut, says("short answer")])
    assert (result.status, result.answer) == ("done", "short answer")
    notes = [e for e in events if e.type == "tool.result" and e.feedback == "length"]
    assert notes and "output limit" in str(notes[0].output)


async def test_a_missing_case_value_in_a_plant_s_issues_says_how_to_get_it():
    """The design lead tried 12 times to put a case value in the plant; now the issue routes it."""
    from geomind.tools.gemini.plants import routed_issue

    issue = {"path": "site.air.pressure", "code": "missing_value", "message": "missing"}
    routed = routed_issue(issue)
    assert "case change needed: site.air.pressure" in routed["suggestions"][0]
    plant_issue = {"path": "d0.drainage_radius", "code": "missing_value", "message": "missing"}
    assert routed_issue(plant_issue) == plant_issue


async def test_a_plant_s_issues_are_compact_enough_to_stay_in_the_history():
    """Round 2 re-read one read_plant result 29 times: its 110 issues took 30k characters."""
    import json

    from geomind.tools.gemini.plants import read_plant
    from tests.fixtures.calls import call as dispatched

    output = (await dispatched(read_plant, {"plant_class": "HeatingHeatPumpCoolingPlant"})).output
    issues = output["issues"]
    assert len(json.dumps(issues)) < 22000
    first = next(item for item in issues if item["path"] == "params.d0.drainage_radius")
    assert first["units"] == "ft|in|km|m|mm" and not first["message"].startswith("d0.")
    assert read_plant.keeps_result


async def test_the_same_failing_call_again_and_again_ends_the_agent_s_run():
    """Round 2 sent build_plant with an empty plant 35 times; the third identical failure stops."""
    script = [uses(call("run_code", f"c{index}", code="print(1)")) for index in range(5)]
    script.append(says("never reached"))
    result, _, _ = await run(script)
    assert result.stop_reason == "error" and "same call failed 3 times" in result.message


def test_build_plant_s_schema_names_the_plant_file_s_keys():
    """The plant was a bare object in the schema, and the model sent {} 35 times."""
    import gemini as gm

    from geomind.tools.gemini.plants import plant_schema

    schema = plant_schema()
    assert set(schema["required"]) == {"format", "kind", "name"}
    assert set(schema["properties"]) == set(gm.plants.schema()["properties"])
    assert schema["minProperties"] == 3


async def test_an_empty_plant_says_what_a_plant_file_needs():
    """An empty plant is named as such, with the smallest file that builds as an example."""
    import json

    from geomind.tools.gemini.plants import build_plant
    from geomind.tools.gemini.skeleton import plant_skeleton
    from tests.fixtures.calls import call as dispatched

    error = (await dispatched(build_plant, {"name": "p", "plant": {}})).output["error"]
    assert error["path"] == "plant" and "empty" in error["message"]
    assert json.loads(error["suggestions"][0]) == {**plant_skeleton(), "type": "<plant class>"}
