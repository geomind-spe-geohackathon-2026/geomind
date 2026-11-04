"""The ``tool`` criterion's ``succeeded`` option: a call that returned an error does not count."""

from evals.run import Outcome
from evals.tasks_format import ToolCriterion

PLAIN = ToolCriterion(kind="tool", tool="delegate")
SUCCEEDED = ToolCriterion(kind="tool", tool="delegate", succeeded=True)


def test_a_failed_delegate_fails_succeeded_only():
    """A delegate call whose nested run failed passes the plain criterion, not ``succeeded``."""
    failed = Outcome(name="t", tools=["read_case", "delegate"], succeeded=["read_case"])
    assert PLAIN.problem(failed) is None
    assert "delegate" in SUCCEEDED.problem(failed)


def test_an_ok_delegate_passes_both():
    """A delegate call without an error passes both criteria."""
    ok = Outcome(name="t", tools=["delegate", "delegate"], succeeded=["delegate"])
    assert PLAIN.problem(ok) is None
    assert SUCCEEDED.problem(ok) is None


def test_not_called_still_fails_succeeded():
    """A tool never called fails ``succeeded`` with the called message."""
    none = Outcome(name="t", tools=["read_case"], succeeded=["read_case"])
    assert "called = False" in SUCCEEDED.problem(none)
