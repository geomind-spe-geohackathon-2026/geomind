"""The state of a run, which ``apply`` in ``recovery.py`` builds, and why a run stops."""

from dataclasses import dataclass, field
from typing import Any

from geomind.context import ProblemState
from geomind.types import Action, Cancel, Message, Record, Request, ToolCall, Usage


@dataclass
class Stop:
    """Why a run stops now: exactly one reason."""

    reason: str
    message: str | None = None
    answer: Any = None
    request: Request | None = None


def is_cancel(decision):
    """Tell whether a decision ends the run as cancelled."""
    return isinstance(decision, Cancel)


class PendingAction(Record):
    """What a paused run waits to do: where it stopped, the exact call, and any nested run."""

    request: Request
    point: str
    call: ToolCall | None = None
    child: str | None = None


@dataclass
class RunState:
    """Everything a run is.

    ``apply`` is the only code that changes it, one event at a time, so the live state and a
    rebuild from the log are equal by construction. ``action``, ``calls``, ``results``, ``allowed``
    and ``started`` describe the open step, so a run continues inside a step without repeating what
    the log already holds. ``allowed`` holds approved call ids, and ``llm`` or ``finish`` for an
    approved pause at those points. ``problem`` is the problem state, shared by the whole tree of
    runs. ``is_refused`` says the answer of this step went back to the
    model, so the step closes instead of proposing it again. ``sequence`` is the last number of the
    whole log, nested runs included.
    """

    run_id: str = ""
    root: str = ""
    parent: str | None = None
    parent_step: int | None = None
    chat: str | None = None
    project: str | None = None
    agent_class: str = ""
    agent: str = ""
    loop: str | None = None
    loop_state: dict[str, Any] = field(default_factory=dict)
    max_steps: int = 0
    settings: dict[str, Any] = field(default_factory=dict)
    messages: list[Message] = field(default_factory=list)
    problem: ProblemState = field(default_factory=ProblemState)
    step: int = 0
    in_step: bool = False
    action: Action | None = None
    calls: list[ToolCall] = field(default_factory=list)
    results: dict[str, Message] = field(default_factory=dict)
    stored: dict[str, str] = field(default_factory=dict)
    allowed: list[str] = field(default_factory=list)
    started: list[str] = field(default_factory=list)
    usage: Usage = Usage()
    step_usage: Usage = Usage()
    pending: PendingAction | None = None
    failures: dict[str, int] = field(default_factory=dict)
    output_failures: int = 0
    is_refused: bool = False
    has_answer: bool = False
    answer: Any = None
    status: str = "running"
    stop_reason: str | None = None
    message: str | None = None
    sequence: int = 0
