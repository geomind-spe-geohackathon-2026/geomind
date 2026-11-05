"""The state of a run, which ``apply`` in ``recovery.py`` builds, and why a run stops."""

from dataclasses import dataclass, field
from typing import Any

from geomind.context import ProblemState
from geomind.types import Action, Cancel, Message, Record, Request, ToolCall, Usage


@dataclass
class Stop:
    """Why a run stops now: exactly one reason; ``is_crash`` keeps the message out of the result."""

    reason: str
    message: str | None = None
    answer: Any = None
    request: Request | None = None
    is_crash: bool = False


def is_cancel(decision):
    """Tell whether a decision ends the run as cancelled."""
    return isinstance(decision, Cancel)


class PendingAction(Record):
    """What a paused run waits to do: where it stopped, the exact call, and any nested run."""

    request: Request
    point: str
    call: ToolCall | None = None
    child: str | None = None


@dataclass(frozen=True)
class Succeeded:
    """One call of the run that ran with success: its key (tool and whole input), and its result.

    ``outline`` is the short text of the result, ``reference`` the stored result's key.
    """

    key: str
    tool: str
    step: int
    reference: str | None
    outline: str


@dataclass
class RunState:
    """Everything a run is.

    ``apply`` is the only code that changes it, one event at a time, so the live state and a
    rebuild from the log are equal by construction. ``action``, ``calls``, ``results``, ``allowed``
    and ``started`` describe the open step, so a run continues inside a step without repeating what
    the log already holds. ``succeeded`` lists the calls that ran with success, in order, and
    ``same_calls`` counts in a row the steps whose call was answered from one of them
    (``same_result``). ``allowed`` holds approved call ids, and ``llm`` or ``finish`` for an
    approved pause at those points. ``problem`` is the problem state, shared by the whole tree of
    runs. ``is_refused`` says the answer of this step went back to the
    model, so the step closes instead of proposing it again. ``sequence`` is the last number of the
    whole log, nested runs included. ``usage`` and ``step_usage`` include what nested runs spent,
    so they are for budgets and reports only; ``last_input_tokens`` is the input the provider
    counted for this run's own last model call, none after its compaction, and is what a context
    decision reads beside the size of the run's own messages. ``call_usage`` is what the open
    step's own model calls spent (its call and a compaction before it, never a nested run),
    ``call_input_tokens`` the input of its provider call (``None`` before one or for a rule) and
    ``context_window`` the window its ``step.started`` named; ``step.finished`` reports them.
    ``reported_usage`` is the running total the last ``usage`` event sent.
    """

    run_id: str = ""
    root: str = ""
    parent: str | None = None
    parent_step: int | None = None
    chat: str | None = None
    project: str | None = None
    agent_class: str = ""
    agent: str = ""
    instance: str | None = None
    loop: str | None = None
    loop_state: dict[str, Any] = field(default_factory=dict)
    max_steps: int = 0
    step_grant: int = 0
    is_cut: bool = False
    cut_tokens: int = 0
    last_failure: str | None = None
    last_failure_step: int | None = None
    repeated: int = 0
    succeeded: list[Succeeded] = field(default_factory=list)
    same_calls: int = 0
    same_call_step: int | None = None
    questions: int = 0
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
    last_input_tokens: int = 0
    call_usage: Usage = Usage()
    call_input_tokens: int | None = None
    context_window: int | None = None
    reported_usage: Usage | None = None
    pending: PendingAction | None = None
    failures: dict[str, int] = field(default_factory=dict)
    failure_steps: dict[str, int] = field(default_factory=dict)
    blocked: dict[str, Any] = field(default_factory=dict)
    failure_versions: dict[str, Any] = field(default_factory=dict)
    output_failures: int = 0
    is_refused: bool = False
    has_answer: bool = False
    answer: Any = None
    status: str = "running"
    stop_reason: str | None = None
    message: str | None = None
    sequence: int = 0
