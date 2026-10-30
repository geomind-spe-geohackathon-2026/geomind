"""Run results and the status of a stop reason."""

import pytest

from swarmax.core.types import RunResult, status_of


@pytest.mark.parametrize(
    ("stop_reason", "status"),
    [
        ("answer", "done"),
        ("finish", "done"),
        ("request", "waiting"),
        ("denied", "failed"),
        ("step_limit", "failed"),
        ("error", "failed"),
        ("cancelled", "cancelled"),
    ],
)
def test_status_follows_the_contract(stop_reason, status):
    """Every stop reason has one contract status."""
    assert status_of(stop_reason) == status


def test_result_defaults_to_no_usage():
    """A fresh result has zero usage."""
    assert RunResult(run_id="r", status="done").usage.cost == 0
