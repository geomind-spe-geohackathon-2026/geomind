"""A brief in gemini's terms: the schedule rules come from the brief, never from the code."""

import pytest

from geomind.context import Brief, preset, with_changes
from geomind.errors import ToolError
from geomind.tools.gemini.brief import schedule_rules, set_brief, si, text
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

HACKATHON = preset("hackathon_2027")


def test_the_hackathon_rules_are_its_hard_limits():
    """Doublets run between 50 and 300 m3/h and cool the brine by at most 40 K."""
    rules = schedule_rules(HACKATHON)
    assert rules["doublet_flow"] == {"min": "50 m3/h", "max": "300 m3/h"}
    assert rules["max_brine_cooling"] == "40 K"


def test_the_operating_days_wait_for_gemini():
    """``gm.schedule`` raises ``NotImplementedYet`` for anything but ``None``, so none is passed."""
    assert HACKATHON.operating_days == 330
    assert schedule_rules(HACKATHON)["operating_days"] is None


def test_geothermal_heat_comes_first():
    """The doublets, then a heat pump, then a boiler cover the demand."""
    assert schedule_rules(HACKATHON)["order"] == ["geothermal", "heat_pump", "boiler"]


def test_another_brief_gives_other_rules():
    """A brief's own flow and brine cooling reach ``gm.schedule``, as texts or Values."""
    brief = with_changes(
        HACKATHON,
        {"doublet_flow": {"max": {"value": 200, "unit": "m3/h"}}, "max_brine_cooling": "30 K"},
    )
    rules = schedule_rules(brief)
    assert rules["doublet_flow"] == {"min": "50 m3/h", "max": "200 m3/h"}
    assert rules["max_brine_cooling"] == "30 K"


def test_a_brief_without_flow_limits_cannot_be_scheduled():
    """``gm.schedule`` needs the flow range and the brine cooling: the error says what to set."""
    with pytest.raises(ToolError, match="doublet_flow.min, doublet_flow.max, max_brine_cooling"):
        schedule_rules(Brief(source="user"))


def test_amounts_convert_through_gemini_units():
    """A text and a Value are the same amount; ``gm.units`` converts them."""
    assert text({"value": 100, "unit": "degC"}) == "100 degC"
    assert si("100 degC", "K") == pytest.approx(373.15)
    assert si({"value": 300, "unit": "m3/h"}, "m3/s") == pytest.approx(300 / 3600)


async def test_set_brief_loads_a_preset_into_the_state():
    """The preset becomes the state's brief, as the session records the change."""
    session = StubSession()
    result = await call(set_brief, {"preset": "hackathon_2027"}, session)
    assert result.output["brief"]["source"] == "hackathon_2027"
    change = session.changes[-1][0]
    assert (change["op"], change["path"]) == ("replace", "/brief")
    assert Brief.model_validate(change["value"]) == HACKATHON


async def test_set_brief_applies_the_user_s_values():
    """Changes to a preset make the user's brief."""
    session = StubSession()
    changes = {"doublets": {"max": 1}, "heating": {"supply": "80 degC"}}
    result = await call(set_brief, {"preset": "hackathon_2027", "changes": changes}, session)
    brief = result.output["brief"]
    assert (brief["source"], brief["doublets"]["max"], brief["heating"]["supply"]) == (
        "user",
        1,
        "80 degC",
    )


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        (
            {"max_brine_cooling": "40 m3/h"},
            "max_brine_cooling = '40 m3/h': expected a unit of temperature_difference",
        ),
        ({"doublet_flow": {"max": "300 cubic"}}, "doublet_flow.max = '300 cubic'"),
        ({"doublet": 2}, "changes: doublet"),
    ],
)
async def test_set_brief_refuses_what_gemini_cannot_read(changes, message):
    """A wrong unit, an unknown unit and an unknown field are input errors that say what to fix."""
    result = await call(set_brief, {"changes": changes})
    assert result.is_error and message in result.output["error"]["message"]


async def test_set_brief_refuses_an_unknown_preset():
    """The message lists the presets."""
    result = await call(set_brief, {"preset": "hackathon"})
    assert result.is_error and "hackathon_2027" in result.output["error"]["message"]
