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


class CallContext(Record):
    """The context of one model call: ``used`` is its input tokens, ``remaining`` what is left.

    ``window`` and ``remaining`` are ``None`` when the model's window is unknown.
    """

    used: int
    window: int | None = None
    remaining: int | None = None


class SessionContext(Record):
    """The context of one session: the largest and the last input of its own model calls."""

    peak_used: int
    last_used: int
    window: int | None = None


class SessionUsage(Record):
    """What one session (one run of one agent, ``session`` = its run id) spent on its own calls.

    ``usage`` holds this session's model calls only, never those of its nested runs; ``steps``
    and ``tool_calls`` count its steps and its tools started. ``context`` is ``None`` for a
    session that made no model call (an agent that decides by rule).
    """

    session: str
    agent: str
    parent: str | None = None
    model: str | None = None
    steps: int = 0
    tool_calls: int = 0
    usage: Usage = Usage()
    context: SessionContext | None = None


class AgentUsage(Record):
    """The sessions of one agent path added up: ``sessions`` counts them."""

    agent: str
    sessions: int
    steps: int = 0
    tool_calls: int = 0
    usage: Usage = Usage()


class TotalUsage(Record):
    """The sum of every session of a run tree, each model call counted once."""

    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    cost: float = 0.0
    steps: int = 0
    tool_calls: int = 0


class RunResult(Record):
    """How a run ended, or that it waits for an answer to ``request``.

    ``message`` says why a run stopped without an answer; a crash keeps its text in the log only.
    ``suggestions`` are the next steps, ``[{label, message}]``, the same list as the run's
    ``run.finished`` event: a root run that ended ``done`` has one to three, any other run none.
    ``sessions``, ``agents`` and ``total`` are those of the root run's ``run.finished``, ``None``
    for a nested run and a run that waits; ``usage`` stays and equals ``total``.
    """

    run_id: str
    status: str
    answer: Any = None
    request: Request | None = None
    usage: Usage = Usage()
    steps: int = 0
    stop_reason: str | None = None
    message: str | None = None
    suggestions: list[dict[str, str]] | None = None
    sessions: list[SessionUsage] | None = None
    agents: list[AgentUsage] | None = None
    total: TotalUsage | None = None
