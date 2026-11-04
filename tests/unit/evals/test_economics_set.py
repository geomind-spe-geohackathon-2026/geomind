"""A case task whose brief needs economics fails when the run ends with none set (#121)."""

from evals.run import Outcome
from evals.tasks_format import StateCriterion

ECONOMICS = StateCriterion(kind="state", path="/case/economics")
CASE = {"format": 1, "kind": "case", "time": {"start": "2027-01-01"}}


def test_a_case_without_economics_fails():
    """The case of nemotron's project run: set and accepted, no economics."""
    outcome = Outcome(name="t", state={"case": CASE})
    assert ECONOMICS.problem(outcome) == "state: /case/economics is not set"
    assert ECONOMICS.problem(Outcome(name="t")) == "state: /case/economics is not set"


def test_a_case_with_its_economics_file_passes():
    """``set_case(economics=...)`` names the economics file in the case."""
    outcome = Outcome(name="t", state={"case": {**CASE, "economics": "economics.json"}})
    assert ECONOMICS.problem(outcome) is None
