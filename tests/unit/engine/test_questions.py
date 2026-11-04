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


RH_390 = (
    "Please give each one with its unit:\n\n"
    "1. site.fluid.dissolved_gas.N2 — mole fraction of nitrogen in the produced brine's "
    "dissolved gas (unit: - / mol% / ppm).\n"
    "4. site.air.relative_humidity — outside air relative humidity (unit: number 0–1). "
    "Needed for ambient conditions.\n"
    "11. utilities.gas.composition.O2 — mole fraction of oxygen in the grid gas (unit: - / "
    "mol% / ppm).\n\n"
    'You may leave any value unset by answering "unknown" or "leave open" for it.'
)
"""Part of request-390 (case lead) of run d0ce14a9 (E2E-3)."""
RH_390_ANSWER = (
    "1, 2, 3: unknown. 4 (outside air relative humidity): use Trondheim, Norway, 2027 data, else "
    "2026 or 2025. 5-8: the return temperatures are the designers' choice. 9, 10, 11, 12: unknown."
)
RH_CONFIRM = (
    "site.air.relative_humidity: I found hourly relative humidity from Open-Meteo for Trondheim, "
    "Norway (63.43049, 10.39506, elevation 12 m), 2026-01-12 to 2026-02-02, timezone "
    "Europe/Oslo, unit % (values 39-97). The case key expects a number between 0 and 1. Confirm "
    "this series as the source for site.air.relative_humidity? (Origin: open-meteo / "
    "openmeteo_get_historical / 2026-11-04T13:49:07+00:00)\n\n"
    "The following values remain unset (you said unknown or designers' choice): "
    "site.fluid.dissolved_gas.N2, utilities.gas.composition.O2."
)
"""The refused question after read_mcp (E2E-3)."""


def test_a_value_found_after_the_answer_is_confirmed():
    """E2E-3: the earlier answer pointed to a source; the value found there is a new question."""
    events = asked("case-lead", "c1", RH_390, 390, RH_390_ANSWER)
    found = answered_paths(events, Request(kind="question", message=RH_CONFIRM))
    assert set(found) == {"site.fluid.dissolved_gas.N2", "utilities.gas.composition.O2"}
    message = asking_new(Request(kind="question", message=RH_CONFIRM), found).message
    assert message.startswith(RH_CONFIRM) and "Answer only" not in message


AIR_309 = (
    "2) Site air conditions:\n"
    "   - site.air.temperature — outside air temperature, value with unit (e.g. 10 °C), "
    "or say constant\n"
    "   - site.air.relative_humidity — outside air relative humidity, a number (e.g. 0.7 for "
    "70%)\n"
    "   - site.air.pressure — outside air pressure, value with unit (e.g. 101325 Pa), OR the "
    "site elevation in m (I'll derive ISA pressure from it)"
)
"""Part of request-309 (case lead) of run 4b6a542c (E2E-7)."""
AIR_CONFIRM = (
    "Please confirm or provide the following case values:\n\n"
    "CONFIRM (value not from any project file):\n"
    "- site.air.pressure = 101108.95 Pa — from open-meteo Trondheim location search "
    "(elevation 18 m), converted via ISA (ISO 2533:1975). Confirm this pressure?\n\n"
    "PROVIDE (needed, no value yet):\n"
    "- site.air.temperature — value and unit (e.g. °C).\n"
    "- site.air.relative_humidity — number (fraction or percent). What value should the case "
    "use?\n\n"
    "Reply: confirm the pressure, and give temperature and humidity values (or say unknown/leave "
    "open)."
)


def test_the_same_question_about_the_same_value_stays_answered_a_new_value_does_not():
    """E2E-7: the pressure from the elevation is confirmed; the provide items keep their answer."""
    events = asked("case-lead", "c1", AIR_309, 309, "use Trondheim, Norway, 2027 data")
    request = Request(kind="question", message=AIR_CONFIRM)
    found = answered_paths(events, request)
    assert set(found) == {"site.air.temperature", "site.air.relative_humidity"}
    assert set(found) != named_paths(AIR_CONFIRM)
    message = asking_new(request, found).message
    assert "site.air.pressure" not in message[len(AIR_CONFIRM) :] and "Answer only" not in message
    again = asked("case-lead", "c2", AIR_CONFIRM, 400, "confirmed")
    assert "site.air.pressure" in answered_paths(events + again, request)


GAS_521 = (
    "3. site.air.pressure — 101108.95 Pa from 18m elevation (ISA ISO 2533:1975); confirm?\n\n"
    "Unknown — leave open or provide:\n"
    "- site.fluid.dissolved_gas.N2, .H2S; site.fluid.sand_concentration\n"
    "- utilities.electricity.co2_intensity, .import_limit, .export_limit\n"
    "- utilities.gas.composition.CH4, C2H6, C3H8, CO2, N2, O2; utilities.gas.heating_value\n"
    "- initial_state\n\n"
    "Economics: not yet set. Provide values or I'll use cost-catalogue rows (2015 EUR)."
)
"""Part of request-521 (case lead) of run 6f680c9b (E2E-11)."""


def test_shortened_list_items_are_paths():
    """E2E-11: ``.H2S`` and ``C2H6`` after a full path name the paths of its parent."""
    paths = named_paths(GAS_521)
    assert {"site.fluid.dissolved_gas.H2S", "utilities.electricity.export_limit"} <= paths
    gas = {f"utilities.gas.composition.{name}" for name in ("CH4", "C2H6", "C3H8", "CO2", "N2")}
    assert gas | {"utilities.gas.composition.O2", "utilities.gas.heating_value"} <= paths
    assert named_paths("site.air.pressure, which is missing, and site.air.temperature / RH") == {
        "site.air.pressure",
        "site.air.temperature",
        "site.air.RH",
    }
    assert named_paths("demand.heating.power and demand.cooling.power)") == {
        "demand.heating.power",
        "demand.cooling.power",
    }


def test_no_answer_only_line_when_the_question_carries_a_confirmation():
    """E2E-11: the pressure confirmation and the economics stay asked; no "Answer only"."""
    events = asked("case-lead", "c1", MANY, 346, "1-3: use Trondheim, Norway, 2027 data")
    events += asked("case-lead", "c2", "site.fluid.dissolved_gas.N2, .H2S?", 350, "unknown")
    request = Request(kind="question", message=GAS_521)
    found = answered_paths(events, request)
    assert set(found) == {"site.fluid.dissolved_gas.N2", "site.fluid.dissolved_gas.H2S"}
    message = asking_new(request, found).message
    assert message.startswith(GAS_521) and "Answer only" not in message


def test_the_reused_answer_does_not_tell_the_model_to_drop_a_found_value():
    """E2E-7: the note says a value found since is asked with its source, not left open."""
    events = asked("case-lead", "c1", AIR_309, 309, "use Trondheim, Norway, 2027 data")
    note = reused_answer(answered_paths(events, Request(kind="question", message=AIR_309)))
    assert "stays open" not in note and "confirm" in note
