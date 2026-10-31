"""The result of a run and how a stop reason maps to the contract status."""

from typing import Any

from geomind.types.decisions import Request
from geomind.types.messages import Record, Usage

STATUS_OF_STOP = {
    "answer": "done",
    "finish": "done",
    "request": "waiting",
    "denied": "failed",
    "step_limit": "failed",
    "error": "failed",
    "not_implemented": "failed",
    "cancelled": "cancelled",
}


def status_of(stop_reason):
    """Return the contract status of a stop reason."""
    return STATUS_OF_STOP[stop_reason]


class RunResult(Record):
    """How a run ended, or that it waits for an answer to ``request``."""

    run_id: str
    status: str
    answer: Any = None
    request: Request | None = None
    usage: Usage = Usage()
    steps: int = 0
    stop_reason: str | None = None
