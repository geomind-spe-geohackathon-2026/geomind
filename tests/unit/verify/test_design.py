"""The verdict on the design the problem state names."""

import asyncio

import pytest

import geomind as gd
from geomind.context import preset, with_changes
from geomind.context.state import ProblemState
from geomind.engine import Context
from geomind.verify.design import verify_design
from tests.fixtures.calls import call
from tests.fixtures.hackathon import base_spec
from tests.fixtures.sessions import StubSession


@pytest.fixture(scope="module")
def stored():
    """Return a session with the base design and its run of three winter days."""
    import gemini as gm

    session = StubSession()

    async def store():
        tools = gd.tools.gemini
        await call(tools.build_plant, {"plant": base_spec(gm), "name": "base"}, session)
        window = {"design": "design/base", "start": "2027-01-01", "end": "2027-01-03"}
        return (await call(tools.simulate, window, session)).output["reference"]

    return session, asyncio.run(store())


def verdict(session, design=None, result=None, brief=None):
    """Return the verdict for a problem state naming a design, a result and a brief."""
    problem = ProblemState(
        design={"reference": design} if design else {},
        verification={"result": result} if result else {},
        brief=brief,
    )
    return verify_design(Context(problem=problem, session=session))


def test_the_named_design_is_checked_on_its_stored_run(stored):
    """The checks of gemini run again; the base design passes."""
    session, result = stored
    found = verdict(session, "design/base", result)
    assert found["passed"] is True
    assert found["checks"]


@pytest.mark.parametrize(
    ("design", "result", "name"),
    [
        ("design/base", None, "verification_missing"),
        (None, "result/x", "verification_missing"),
        ("design/base", "result/missing", "result_unknown"),
    ],
)
def test_what_cannot_be_checked_fails_with_its_reason(stored, design, result, name):
    """A missing or unknown result never passes."""
    session, _ = stored
    found = verdict(session, design, result)
    assert found["passed"] is False
    assert found["failures"] == [{"name": name, "domain": "coupled"}]
    assert found["reason"]


def test_a_result_that_ran_on_the_brief_passes(stored):
    """The run's demand and rules are the hackathon preset's, as the brief says."""
    session, result = stored
    assert verdict(session, "design/base", result, preset("hackathon_2027"))["passed"] is True


@pytest.mark.parametrize(
    "changes",
    [
        {"demand": {"cooling": "profile/more-cooling"}},
        {"max_brine_cooling": "30 K"},
    ],
)
def test_a_result_that_ran_on_another_demand_or_rules_is_off_the_brief(stored, changes):
    """A run on gemini's cooling profile, or the 40 K rule, does not verify another brief."""
    session, result = stored
    brief = with_changes(preset("hackathon_2027"), changes)
    found = verdict(session, "design/base", result, brief)
    assert found["passed"] is False
    assert found["failures"] == [{"name": "result_off_brief", "domain": "coupled"}]
    assert "simulate the design on the brief" in found["reason"]
