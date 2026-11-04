"""A value is asked once per run tree: the questions of the end-to-end run, as recorded."""

from geomind.engine.questions import earlier_answer, named_paths, reused_answer
from geomind.types import Request
from geomind.types.events import RequestMade, ToolRecorded
from geomind.types.messages import ToolCall

DESIGN_LEAD = (
    "The plant sizing requires `site.air.pressure` (atmospheric pressure at the site), which is "
    "missing from the case. gemini needs it to check the plant against the case (air boundary for "
    "the compression cooler). Please provide the site air pressure (e.g., 1.013 bar or similar)."
)
CASE_LEAD = (
    "The case is missing site.air.pressure. gemini needs it to check the plant against the case "
    "- it is the air boundary for the compression_cooler, which rejects the chiller condenser "
    "heat to the atmosphere. Please provide site.air.pressure, in the pressure unit you use (the "
    "case uses bar(g) for reservoir pressure). Name the path, the unit and the value."
)
"""request-1962 (design lead) and request-2055 (case lead, relayed by the project lead)."""


def asked(run_id, call_id, message, sequence, answer):
    """Return the request and answer events of one question of a run."""
    request = Request(kind="question", message=message, id=f"request-{sequence}", call_id=call_id)
    call = ToolCall(id=call_id, name="ask_user", input={"question": message})
    common = {"run_id": run_id, "time": "t", "agent": "a"}
    made = RequestMade(sequence=sequence, request=request, point="tool", call=call, **common)
    result = ToolRecorded(
        sequence=sequence + 2,
        index=1,
        call_id=call_id,
        tool="ask_user",
        output=answer,
        source="answer",
        **common,
    )
    return [made, result]


def test_both_questions_name_the_one_path():
    """Backquoted or not, the paths are the case's dotted keys; other words are not."""
    assert named_paths(DESIGN_LEAD) == {"site.air.pressure"} == named_paths(CASE_LEAD)
    assert named_paths("Which ranges for heat_pump.capacity?") == frozenset()


def test_the_case_lead_s_question_reuses_the_design_lead_s_answer():
    """The second question of the run is answered by the first answer, in another nested run."""
    events = asked("design-lead", "c1", DESIGN_LEAD, 1962, "unknown")
    found = earlier_answer(events, Request(kind="question", message=CASE_LEAD))
    assert found is not None and found[1] == "unknown" and found[0].id == "request-1962"
    note = reused_answer(*found)
    assert "Not asked again" in note and "site.air.pressure" in note and "'unknown'" in note


def test_a_question_on_other_or_more_paths_is_asked():
    """Only exactly the same paths reuse an answer; a question naming none is always asked."""
    events = asked("design-lead", "c1", DESIGN_LEAD, 1962, "unknown")
    more = Request(kind="question", message="site.air.pressure and site.air.temperature?")
    assert earlier_answer(events, more) is None
    assert earlier_answer(events, Request(kind="question", message="Go on?")) is None
    assert earlier_answer([], Request(kind="question", message=CASE_LEAD)) is None


def test_an_answer_of_a_tool_that_acts_on_it_is_its_text():
    """``ask_economics`` keeps the user's text under ``answer``."""
    events = asked("case-lead", "c1", "economics.discount_rate?", 5, {"answer": "0.05"})
    found = earlier_answer(events, Request(kind="question", message="economics.discount_rate"))
    assert found[1] == "0.05"
