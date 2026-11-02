"""The verdict on the design the problem state names."""

import pytest

from geomind.context import ProblemState
from geomind.engine import Context
from geomind.tools.gemini.case import merge_patch
from geomind.verify.design import verify_design
from tests.fixtures.cases import example_names
from tests.fixtures.stored_runs import variant_run, warm_runs


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run the stored runs once, outside the event loop of a test."""
    warm_runs()


def verdict(context, design=None, result=None, case=None):
    """Return the verdict for a problem state naming a design, a result and a case."""
    problem = ProblemState(
        design={"reference": design} if design else {},
        verification={"result": result} if result else {},
        case=context.problem.case if case is None else case,
    )
    return verify_design(Context(problem=problem, session=context.session))


@example_names
def test_the_named_design_is_checked_on_its_stored_run(name):
    """Gemini judges the stored run again on the case it ran on; the passing design passes."""
    context, design, result = variant_run(name, "base")
    found = verdict(context, design, result)
    assert found["passed"] is True
    assert found["checks"]


def test_a_design_that_fails_gemini_s_checks_is_routed_by_domain():
    """The 15 MW cooling peak fails the cold delivered; the failure names the domain to fix it."""
    context, design, result = variant_run("hackathon_2026", "cooling_peak")
    found = verdict(context, design, result)
    assert found["passed"] is False
    assert [(item["name"], item["kind"], item["domain"]) for item in found["failures"]] == [
        ("cold_delivered", "requirement", "sizing"),
        ("cooling_supply_temperature", "requirement", "sizing"),
    ]


@pytest.mark.parametrize(
    ("design", "result", "name"),
    [
        ("design/candidate", None, "verification_missing"),
        (None, "result/x", "verification_missing"),
        ("design/candidate", "result/missing", "result_unknown"),
    ],
)
def test_what_cannot_be_checked_fails_with_its_reason(design, result, name):
    """A missing or unknown result never passes."""
    context, _, _ = variant_run("shallow_district", "base")
    found = verdict(context, design, result)
    assert found["passed"] is False
    assert found["failures"][0]["name"] == name
    assert found["reason"]


async def test_a_result_of_another_plant_than_the_design_is_stale():
    """The design was changed after the run: its result does not verify it."""
    context, design, result = variant_run("hackathon_2026", "base")
    other = dict(context.session.artifacts[design])
    context.session.artifacts["design/changed"] = {**other, "name": "changed"}
    found = verdict(context, "design/changed", result)
    assert found["failures"][0]["name"] == "stale_result"


def test_a_result_that_ran_on_another_case_than_the_state_s_is_off_the_case():
    """A limit changed in the state after the run makes the run stale; simulate again."""
    context, design, result = variant_run("hackathon_2026", "base")
    changed = merge_patch(context.problem.case, {"environment": {"air": {"temperature": None}}})
    found = verdict(context, design, result, case=changed)
    assert found["passed"] is False
    assert found["failures"][0]["name"] == "result_off_case"
    assert "simulate the design on the state's case" in found["reason"]
