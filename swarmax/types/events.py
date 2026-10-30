"""Every event of a run: the public ones of the contract and the internal ones of the log.

``type`` strings are stable identifiers: a change is a new version, recorded in ``events.md``.
``is_public`` events go to the browser through ``data()``, which returns exactly the contract
JSON. A public event may hold more fields than ``data()`` shows, because the log is the source of
truth: ``to_dict()`` keeps them all and ``event_from_dict`` restores the event.
"""

from typing import Any, ClassVar

from swarmax.errors import RunError
from swarmax.types.decisions import Request
from swarmax.types.messages import Completion, Message, Record, ToolCall, Usage

EVENT_LOG_VERSION = 1
BASE_FIELDS = ("run_id", "sequence", "time", "agent", "parent")


class Event(Record):
    """One entry of a run's log; ``parent`` is the parent run id of a nested run."""

    type: ClassVar[str]
    is_public: ClassVar[bool] = False
    public_fields: ClassVar[tuple[str, ...]] = ()

    run_id: str
    sequence: int = 0
    time: str = ""
    agent: str = ""
    parent: str | None = None

    def data(self):
        """Return the JSON of this event; an optional field that is ``None`` is left out."""
        dumped = self.model_dump(mode="json")
        names = self.public_fields if self.is_public else set(dumped) - set(BASE_FIELDS)
        values = {name: dumped[name] for name in names if dumped[name] is not None}
        return {**values, "agent": self.agent, "parent": self.parent}

    def to_dict(self):
        """Return every field with the type, for ``event_from_dict``."""
        return {"type": self.type, **self.model_dump(mode="json")}


class RunStarted(Event):
    """A run began; the fields after ``loop`` rebuild it and are not streamed."""

    type: ClassVar[str] = "run.started"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("run", "loop")

    run: str
    loop: str | None = None
    root: str
    agent_class: str
    max_steps: int
    chat: str | None = None
    project: str | None = None
    parent_step: int | None = None
    messages: tuple[Message, ...] = ()
    settings: dict[str, Any] = {}
    loop_state: dict[str, Any] = {}


class StepStarted(Event):
    """A step began."""

    type: ClassVar[str] = "step.started"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("index",)

    index: int


class TextDelta(Event):
    """A piece of streamed model text."""

    type: ClassVar[str] = "text.delta"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("index", "text")

    index: int
    text: str


class ToolStarted(Event):
    """A tool call started."""

    type: ClassVar[str] = "tool.started"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("index", "call_id", "tool", "input")

    index: int
    call_id: str
    tool: str
    input: dict[str, Any] = {}


class ToolFinished(Event):
    """A tool call finished; ``error`` is its message when it failed."""

    type: ClassVar[str] = "tool.finished"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = (
        "index",
        "call_id",
        "output_summary",
        "duration",
        "error",
    )

    index: int
    call_id: str
    output_summary: str
    duration: float
    error: str | None = None


class StepFinished(Event):
    """A step finished; ``usage`` is the usage of this step."""

    type: ClassVar[str] = "step.finished"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("index", "usage")

    index: int
    usage: Usage


class StateChanged(Event):
    """The problem state changed; emitted from S2."""

    type: ClassVar[str] = "state.changed"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("changes",)

    changes: tuple[Any, ...]


class RequestMade(Event):
    """The run waits for the user; ``point`` and ``call`` are the pending action."""

    type: ClassVar[str] = "request"
    is_public: ClassVar[bool] = True

    request: Request
    point: str
    call: ToolCall | None = None

    def data(self):
        """Return the contract JSON, which flattens the request."""
        values = {
            "request": self.request.id,
            "call_id": self.request.call_id,
            "kind": self.request.kind,
            "message": self.request.message,
            "options": list(self.request.options) if self.request.options else None,
        }
        present = {name: value for name, value in values.items() if value is not None}
        return {**present, "agent": self.agent, "parent": self.parent}


class UsageUpdated(Event):
    """The running totals of the run."""

    type: ClassVar[str] = "usage"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("input_tokens", "output_tokens", "cost")

    input_tokens: int
    output_tokens: int
    cost: float


class RunFinished(Event):
    """A run ended; ``message`` says why when it did not end with an answer."""

    type: ClassVar[str] = "run.finished"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("status", "stop_reason", "message")

    status: str
    stop_reason: str
    message: str | None = None
    answer: Any = None


class LLMCompleted(Event):
    """One LLM call: the full completion and the messages sent."""

    type: ClassVar[str] = "llm.completed"

    index: int
    completion: Completion
    messages: tuple[Message, ...] = ()
    duration: float = 0.0


class ToolRecorded(Event):
    """One result, or with ``call_id=None`` feedback to the model about its answer.

    ``source`` says where it came from: ``tool``, ``denied``, ``answer`` or ``interrupted``.
    ``feedback`` is ``output`` for a failed validation of the answer and ``finish`` for a refused
    one. ``usage`` is that of a nested run, added to this run.
    """

    type: ClassVar[str] = "tool.result"

    index: int
    call_id: str | None = None
    tool: str = ""
    input: dict[str, Any] = {}
    output: Any = None
    is_error: bool = False
    is_validation: bool = False
    is_finish: bool = False
    duration: float = 0.0
    source: str = "tool"
    reference: str | None = None
    feedback: str | None = None
    usage: Usage | None = None


class PermissionDecided(Event):
    """One decision: ``allow``, ``deny``, ``ask``, ``answer`` or ``wait``, and what made it.

    ``request`` is set when a user's answer settles a pending request. ``wait`` records that a
    nested run (``child``) paused, so this run waits on the same request. ``input`` is a changed
    tool input.
    """

    type: ClassVar[str] = "permission"

    index: int
    decision: str
    rule: str
    point: str = "tool"
    call_id: str | None = None
    tool: str | None = None
    reason: str | None = None
    input: dict[str, Any] | None = None
    request: Request | None = None
    child: str | None = None
    call: ToolCall | None = None


class Retried(Event):
    """A provider call failed and is tried again."""

    type: ClassVar[str] = "retry"

    attempt: int
    model: str
    error: str
    delay: float


class SandboxProvisioned(Event):
    """A sandbox was created for this run."""

    type: ClassVar[str] = "sandbox.provisioned"

    provider: str


class SandboxClosed(Event):
    """The sandbox of this run was closed or lost."""

    type: ClassVar[str] = "sandbox.closed"

    is_lost: bool = False


class CheckpointSaved(Event):
    """A snapshot of the log up to this event; ``loop_state`` is the state of the loop."""

    type: ClassVar[str] = "checkpoint"

    index: int
    loop_state: dict[str, Any] = {}


class ErrorRaised(Event):
    """An error the run survived or ended with: a callback, a tool bug, a provider failure."""

    type: ClassVar[str] = "error"

    error_class: str
    message: str
    where: str


EVENT_CLASSES = {
    event.type: event
    for event in (
        RunStarted,
        StepStarted,
        TextDelta,
        ToolStarted,
        ToolFinished,
        StepFinished,
        StateChanged,
        RequestMade,
        UsageUpdated,
        RunFinished,
        LLMCompleted,
        ToolRecorded,
        PermissionDecided,
        Retried,
        SandboxProvisioned,
        SandboxClosed,
        CheckpointSaved,
        ErrorRaised,
    )
}


def event_from_dict(data):
    """Rebuild an event from ``Event.to_dict()``."""
    values = dict(data)
    kind = values.pop("type", None)
    if kind not in EVENT_CLASSES:
        raise RunError(f"event type = {kind!r}; expected one of the types in events.md")
    return EVENT_CLASSES[kind].model_validate(values)
