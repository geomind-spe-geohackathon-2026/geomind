"""A value is asked once per run tree: the questions of the end-to-end run, as recorded."""

from geomind.engine.questions import answered_paths, asking_new, named_paths, reused_answer
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
    found = answered_paths(events, Request(kind="question", message=CASE_LEAD))
    [(earlier, text)] = found.values()
    assert text == "unknown" and earlier.id == "request-1962"
    note = reused_answer(found)
    assert "Not asked again" in note and "site.air.pressure" in note and "'unknown'" in note


def test_a_question_naming_no_path_has_no_earlier_answer():
    """A question naming none is always asked, and so is one in a tree without answers."""
    events = asked("design-lead", "c1", DESIGN_LEAD, 1962, "unknown")
    assert answered_paths(events, Request(kind="question", message="Go on?")) == {}
    assert answered_paths([], Request(kind="question", message=CASE_LEAD)) == {}


def test_an_answer_of_a_tool_that_acts_on_it_is_its_text():
    """``ask_economics`` keeps the user's text under ``answer``."""
    events = asked("case-lead", "c1", "economics.discount_rate?", 5, {"answer": "0.05"})
    found = answered_paths(events, Request(kind="question", message="economics.discount_rate"))
    assert found["economics.discount_rate"][1] == "0.05"


MANY = (
    "Please provide each, naming its path and unit:\n\n"
    "1. Time zone for both demand files (needed for demand.heating.power and "
    "demand.cooling.power)\n\n"
    "2. site.air.temperature \u2014 outside air temperature, in \u00b0C.\n\n"
    "3. site.air.relative_humidity \u2014 outside air relative humidity, as a fraction "
    "0\u20131.\n\n"
    "4. site.air.pressure \u2014 outside air pressure, in bar or Pa. The brief gives none.\n\n"
    "5. demand.heating.return_temperature \u2014 heating return temperature, in \u00b0C."
)
"""Part of request-259 (case lead, 19 items) of run 4ca94d6e."""
MANY_ANSWER = (
    "1. UTC (the CSV dates are UTC). 5. and 7. demand.heating.return_temperature and "
    "demand.cooling.return_temperature: the designers' choice. Everything else (2, 3, 4, 6, "
    "8-19): unknown."
)
ALONE = (
    "site.air.pressure is missing from the case. gemini requires it for the atmosphere boundary "
    "(the compression-cooler air loop and heat-loss accounting). It has no default and cannot be "
    "set as a plant value.\n\nPlease give the value for site.air.pressure with its unit, exactly "
    "as your source states it (a pressure unit). I will not offer a value or an example number "
    "of my own."
)
"""request-2872 (case lead, relayed by the project lead), asked again after request-259."""


def test_a_path_answered_inside_a_question_of_many_is_not_asked_alone():
    """The run: site.air.pressure, item 4 of request-259, was asked again as request-2872."""
    events = asked("case-lead", "c1", MANY, 259, MANY_ANSWER)
    found = answered_paths(events, Request(kind="question", message=ALONE))
    assert set(found) == {"site.air.pressure"} == named_paths(ALONE)
    assert "(request-259): " in reused_answer(found) and "8-19): unknown" in reused_answer(found)


def test_a_question_mixing_old_and_new_paths_asks_only_the_new_ones():
    """The earlier answers go with the question, which names the new paths to answer."""
    events = asked("case-lead", "c1", MANY, 259, MANY_ANSWER)
    mixed = Request(kind="question", message="site.air.pressure and site.ground.gradient?")
    found = answered_paths(events, mixed)
    assert set(found) == {"site.air.pressure"}
    message = asking_new(mixed, found).message
    assert message.startswith(mixed.message)
    assert "not asked again: site.air.pressure (request-259)" in message
    assert message.endswith("Answer only site.ground.gradient.")


def test_the_first_answer_of_a_path_stays_its_answer():
    """A later question that named the path again (with the note) does not replace its answer."""
    events = asked("case-lead", "c1", MANY, 259, MANY_ANSWER)
    events += asked("case-lead", "c2", "site.air.pressure and site.ground.gradient?", 300, "30")
    found = answered_paths(events, Request(kind="question", message=ALONE))
    assert found["site.air.pressure"][0].id == "request-259"
