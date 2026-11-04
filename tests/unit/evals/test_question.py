"""The ``question`` criterion: ``contains`` or any of ``contains_any`` (#123)."""

import pytest
from pydantic import ValidationError

from evals.run import Outcome
from evals.tasks_format import QuestionCriterion

ASKED = Outcome(name="t", questions=["annual_operation is a count of 330, not a duration: which?"])


def test_contains_still_reads_as_before():
    """An old task's ``contains`` is one word, case ignored."""
    assert QuestionCriterion(kind="question", contains="ANNUAL_OPERATION").problem(ASKED) is None
    problem = QuestionCriterion(kind="question", contains="doublet").problem(ASKED)
    assert "'doublet'" in problem


def test_any_name_of_the_flaw_passes():
    """A flaw named by its key, not by "doublet" (nemotron): any of the names counts."""
    names = ("doublet", "annual_operation", "count")
    assert QuestionCriterion(kind="question", contains_any=names).problem(ASKED) is None
    missing = QuestionCriterion(kind="question", contains_any=("span", "time.end"))
    assert "['span', 'time.end']" in missing.problem(ASKED)


def test_a_question_criterion_needs_a_text():
    """Neither ``contains`` nor ``contains_any`` is refused when the task loads."""
    with pytest.raises(ValidationError):
        QuestionCriterion(kind="question")
