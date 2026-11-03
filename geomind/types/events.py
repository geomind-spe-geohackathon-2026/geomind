"""Every event of a run: the public ones of the contract and the internal ones of the log.

``type`` strings are stable identifiers: a change is a new version, recorded in ``events.md``.
``is_public`` events go to the browser through ``data()``, which returns exactly the contract
JSON. A public event may hold more fields than ``data()`` shows, because the log is the source of
truth: ``to_dict()`` keeps them all and ``event_from_dict`` restores the event.
"""

from typing import Any, ClassVar

from pydantic import Field, field_validator

from geomind.errors import RunError
from geomind.types.decisions import Request
from geomind.types.messages import Completion, Message, Record, ToolCall, Usage
from geomind.types.patch import operation_problem

BASE_FIELDS = ("run_id", "sequence", "time", "agent", "parent")
LLM_EVENTS = ("llm.completed", "compaction")


PUBLIC_USAGE = ("input_tokens", "output_tokens", "cost")
"""The usage fields of the contract's JSON; ``cached_tokens`` is kept in the log only."""


def public_usage(usage):
    """Return the usage JSON the contract fixes."""
    return {name: usage[name] for name in PUBLIC_USAGE}


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
        if isinstance(values.get("usage"), dict):
            values["usage"] = public_usage(values["usage"])
        return {**values, "agent": self.agent, "parent": self.parent}

    def to_dict(self):
        """Return every field with the type, for ``event_from_dict``."""
        return {"type": self.type, **self.model_dump(mode="json")}


class RunStarted(Event):
    """A run began; the fields after ``loop`` rebuild it and are not streamed.

    NOTE: ``versions`` holds the geomind, gemini and python versions the run began with. A run
    stored by 0.3.0 has none, so the field is optional here while every new run has it. ``models``
    holds the model id of every role (``None`` where a fake run set none); a run stored before
    0.4.2 has none.
    """

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
    problem: dict[str, Any] = {}
    settings: dict[str, Any] = {}
    loop_state: dict[str, Any] = {}
    versions: dict[str, str] = {}
    models: dict[str, str | None] = {}


class StepStarted(Event):
    """A step began; ``model`` is the provider model id it calls.

    NOTE: a run stored by S1 has no ``model``, so the field is optional here while every new step
    has it.
    """

    type: ClassVar[str] = "step.started"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("index", "model")

    index: int
    model: str | None = None


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
    public_fields: ClassVar[tuple[str, ...]] = ("index", "call_id", "tool", "input", "mcp")

    index: int
    call_id: str
    tool: str
    input: dict[str, Any] = {}
    mcp: str | None = None


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
        "mcp",
    )

    index: int
    call_id: str
    output_summary: str
    duration: float
    error: str | None = None
    mcp: str | None = None


class StepFinished(Event):
    """A step finished; ``usage`` is the usage of this step and ``text`` its full assistant text.

    ``text`` is ``""`` when the step wrote none. ``loop_state`` is the state of the loop, stored but
    not streamed.
    """

    type: ClassVar[str] = "step.finished"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("index", "usage", "text")

    index: int
    usage: Usage
    text: str = ""
    loop_state: dict[str, Any] = {}


class StateChanged(Event):
    """The problem state changed.

    ``version`` is the state version after the change, starting at 1. ``changes`` are JSON Patch
    operations in the subset of ``patch.py``.
    """

    type: ClassVar[str] = "state.changed"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = ("version", "changes")

    version: int = Field(ge=1)
    changes: tuple[dict[str, Any], ...]

    @field_validator("changes")
    @classmethod
    def _check_changes(cls, changes):
        """Refuse an operation outside the contract's subset."""
        for change in changes:
            problem = operation_problem(change)
            if problem is not None:
                raise ValueError(problem)
        return changes


class StudyRecorded(Event):
    """A study tool stored its chat artifact ``study/<name>``; sent once, after it is saved.

    ``run`` is the run that called the tool, ``index`` its step and ``call_id`` the call. ``study``
    is the artifact key, ``tool`` the study tool, ``method`` the gemini study method the tool ran,
    ``designs`` the names of the plants the study ran over and ``best`` the reference of the design
    it recommends, left out of ``data()`` when there is none.
    """

    type: ClassVar[str] = "study.recorded"
    is_public: ClassVar[bool] = True
    public_fields: ClassVar[tuple[str, ...]] = (
        "run",
        "index",
        "call_id",
        "study",
        "tool",
        "method",
        "designs",
        "best",
    )

    run: str
    index: int
    call_id: str | None = None
    study: str
    tool: str
    method: str
    designs: tuple[str, ...]
    best: str | None = None


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
            "options": [option.model_dump() for option in self.request.options or ()] or None,
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


class Compacted(Event):
    """Older turns became one summary: ``completion.text``, which replaced ``turns`` turns.

    It holds the whole completion, like ``llm.completed``, so a replay gets the same summary back
    from ``FakeLLM.from_events`` and a run log counts its cost.
    """

    type: ClassVar[str] = "compaction"

    index: int
    completion: Completion
    messages: tuple[Message, ...] = ()
    duration: float = 0.0
    turns: int


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
        StudyRecorded,
        RequestMade,
        UsageUpdated,
        RunFinished,
        LLMCompleted,
        Compacted,
        ToolRecorded,
        PermissionDecided,
        Retried,
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


def events_from_dicts(lines):
    """Rebuild the events of a stored log, leaving out the ones of a type this version lacks.

    NOTE: a log written by a newer version may hold event types this one does not know. Skipping
    them is the forward compatibility rule: every reader of a log ignores unknown event types. A
    line with a known type that does not fit its class still raises.
    """
    return [event_from_dict(line) for line in lines if line.get("type") in EVENT_CLASSES]
