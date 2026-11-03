"""The review: the reviewer's report, then gemini's verdict in code, sorted by owner."""

import json

from geomind.agents import ProjectLead
from geomind.agents.project.review import VERDICT, owner_hint, verdict_of, verdict_text
from tests.fixtures.runs import call, of_type, run, says, uses

FAILED = {
    "passed": False,
    "failures": [{"name": "heating_coverage", "domain": "surface", "detail": "unmet 2 MW"}],
}
PASSED = {"passed": True, "failures": []}


def test_each_failure_names_the_team_it_goes_to_first():
    """A surface failure goes to the design lead's energy and integration engineers."""
    text = verdict_text(verdict_of(FAILED, "design/a"), [])
    assert "heating_coverage (surface, to design_lead (energy systems" in text
    assert owner_hint("case") == "case_lead"


def test_the_same_failure_on_a_changed_design_is_flagged_repeated():
    """Design b fails exactly as design a did: the project lead is told to stop."""
    earlier = [verdict_of(FAILED, "design/a")]
    assert "repeated_failure" in verdict_text(verdict_of(FAILED, "design/b"), earlier)
    assert "repeated_failure" not in verdict_text(verdict_of(FAILED, "design/a"), earlier)
    assert "repeated_failure" not in verdict_text(verdict_of(PASSED, "design/b"), earlier)


async def test_the_review_appends_gemini_s_verdict_and_keeps_a_passed_design(monkeypatch):
    """After the reviewer's run the code checks again; a pass is kept by code, once."""
    kept = []
    monkeypatch.setattr("geomind.agents.project.review.verify_design", lambda _: PASSED)
    monkeypatch.setattr(
        "geomind.agents.project.review.keep_design",
        lambda context, found, rejected: kept.append(rejected),
    )
    script = [
        uses(call("reviewer", "r", task="Verify design.reference on design.result.")),
        says("The design meets the case."),
        says("final"),
    ]
    result, _, events = await run(script, agent=ProjectLead())
    output = next(e for e in of_type(events, "tool.result") if e.tool == "reviewer").output
    assert output.startswith("The design meets the case.")
    line = output.split(VERDICT, 1)[1].splitlines()[0]
    assert json.loads(line)["passed"] is True and kept == [[]]
    assert result.answer == "final"
