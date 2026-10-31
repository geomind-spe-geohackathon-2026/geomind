"""Verification of a design against its requirements and the brief's hard limits."""

import inspect

import pytest

import geomind as gd
from geomind.context import Brief, preset, with_changes
from geomind.context.state import Requirement
from tests.fixtures.hackathon import base_run


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


@pytest.fixture(scope="module")
def january(gm):
    """Return the base design and its January run, which meets every check."""
    return base_run(gm)


def test_requirements_and_limits_are_keywords():
    """The signature of the plan."""
    parameters = inspect.signature(gd.verify.verify).parameters
    assert parameters["requirements"].kind is inspect.Parameter.KEYWORD_ONLY
    assert (parameters["requirements"].default, parameters["limits"].default) == ((), None)


def test_a_design_that_meets_the_brief_passes(january):
    """Every check of gemini passes, and what gemini cannot judge is listed beside."""
    found = gd.verify.verify(*january)
    assert found["passed"] is True
    assert {item["id"] for item in found["not_assessed"]} >= {"operating_days"}


def test_a_requirement_on_an_output_is_a_limit_of_its_target_and_tolerance(january):
    """``metric`` names ``<path>.<output>``; every day must lie within target ± tolerance."""
    requirement = {
        "id": "r1",
        "text": "brine cooled by 5 K",
        "metric": "d0.brine_cooling",
        "target": 5.0,
        "tolerance": 0.5,
    }
    found = gd.verify.verify(*january, requirements=[requirement])
    check = next(
        c
        for c in found["checks"]
        if c["name"] == "d0.brine_cooling" and c["limit"]["value"] == [4.5, 5.5]
    )
    assert check["passed"] is False
    assert found["passed"] is False
    assert {"name": "d0.brine_cooling", "domain": "subsurface"} in found["failures"]


def test_a_requirement_gemini_cannot_check_is_not_assessed(january):
    """A requirement without an output metric is listed with its reason, never passed."""
    requirement = Requirement(id="r2", text="be cheap", metric="lcoh", target=50)
    found = gd.verify.verify(*january, requirements=[requirement])
    entry = next(item for item in found["not_assessed"] if item["id"] == "r2")
    assert entry["status"] == "NOT_ASSESSED"
    assert "'<path>.<output>'" in entry["reason"]


def test_the_hackathon_preset_gives_the_checks_of_a_state_without_a_brief(january):
    """The preset is today's verification: the same checks, the same verdict, nothing not given."""
    with_preset = gd.verify.verify(*january, brief=preset("hackathon_2027"))
    without = gd.verify.verify(*january)
    assert with_preset["passed"] is True
    assert with_preset["checks"] == without["checks"]
    assert with_preset["not_assessed"] == without["not_assessed"]
    assert with_preset["not_given"] == []
    assert "hackathon_2027 preset" in without["brief"]


def test_another_brief_changes_which_checks_pass(january):
    """One doublet, 30 K and an 80 degC supply fail the base design on gemini's own numbers."""
    brief = with_changes(
        preset("hackathon_2027"),
        {"doublets": {"max": 1}, "max_brine_cooling": "30 K", "heating": {"supply": "80 degC"}},
    )
    found = gd.verify.verify(*january, brief=brief.model_dump(mode="json"))
    assert sorted(item["name"] for item in found["failures"]) == [
        "d0.brine_cooling",
        "d1.brine_cooling",
        "doublets",
        "heat_users.supply_in.temperature",
    ]
    cooling = next(item for item in found["checks"] if item["name"] == "d0.brine_cooling")
    assert cooling["value"]["value"] > 30 and cooling["limit"]["value"] == pytest.approx(30.001)


def test_a_limit_the_brief_does_not_give_is_not_checked(january):
    """A brief with the demand only checks no doublet, flow or temperature limit, and says so."""
    brief = Brief(source="user", demand={"heating": "heating_demand", "cooling": "cooling_demand"})
    found = gd.verify.verify(*january, brief=brief)
    names = {item["name"] for item in found["checks"]}
    assert not names & {
        "doublets",
        "d0.flow",
        "d0.brine_cooling",
        "heat_users.supply_in.temperature",
    }
    assert {"heating_grid", "cooling_grid", "heat_users.unmet_demand"} <= names
    assert found["not_given"] == [
        "doublets",
        "doublet_flow",
        "max_brine_cooling",
        "heating.supply",
        "cooling.supply",
        "operating_days",
        "pump_efficiency",
        "volume_balance",
    ]
    assert found["not_assessed"] == []
