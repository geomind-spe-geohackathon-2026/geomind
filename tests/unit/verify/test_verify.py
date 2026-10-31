"""Verification of a design against its requirements and the brief's hard limits."""

import inspect

import pytest

import geomind as gd
from geomind.context.state import Requirement
from tests.fixtures.hackathon import hackathon_run


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


@pytest.fixture(scope="module")
def january(gm):
    """Return gemini's hackathon plant and its January run, which meets every hard limit."""
    return hackathon_run(gm)


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
