"""A failed run fails its task, except a task's own step limit, which the task means to reach."""

from types import SimpleNamespace

from evals.run import run_problem
from evals.tasks_format import Task

MESSAGE = "Design it."
CRITERIA = [{"kind": "tool", "tool": "optimize", "called": False}]


def result(status, stop_reason):
    """Return the part of a ``RunResult`` the check reads."""
    return SimpleNamespace(status=status, stop_reason=stop_reason)


def test_a_task_s_own_step_limit_is_no_failure():
    """``max_steps: 7`` and the run stopped at it: the criteria decide."""
    task = Task(message=MESSAGE, max_steps=7, criteria=CRITERIA)
    assert run_problem(task, result("failed", "step_limit")) is None


def test_a_step_limit_without_one_in_the_task_fails():
    """The deployment's limit is not the task's: the run failed."""
    task = Task(message=MESSAGE, criteria=CRITERIA)
    assert run_problem(task, result("failed", "step_limit")) == "run: step_limit"


def test_any_other_failure_of_a_limited_task_fails():
    """Only the step limit is the task's own end."""
    task = Task(message=MESSAGE, max_steps=7, criteria=CRITERIA)
    assert run_problem(task, result("failed", "error")) == "run: error"
    assert run_problem(task, result("done", "answer")) is None
