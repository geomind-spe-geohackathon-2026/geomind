"""The state of a run, which is also its checkpoint: a snapshot of the log for speed."""

import importlib
from typing import Any

import pydantic
from pydantic import BaseModel, ConfigDict

from swarmax.core.types import Action, Message, Record, Request, ToolCall, Usage
from swarmax.errors import CheckpointError, RunError

CHECKPOINT_VERSION = 1


def class_path(kind):
    """Return the ``module:qualname`` path that events and checkpoints store for a class.

    Together with ``import_class`` this is the only import-by-string in swarmax.
    """
    return f"{kind.__module__}:{kind.__qualname__}"


def import_class(path):
    """Import the class named by a ``class_path`` string."""
    module_name, _, qualname = path.partition(":")
    try:
        value = importlib.import_module(module_name)
        for part in qualname.split("."):
            value = getattr(value, part)
    except (ImportError, AttributeError, ValueError) as error:
        raise RunError(f"import_class: path = {path!r}; expected an importable class") from error
    return value


class PendingAction(Record):
    """What a paused run waits to do: where it stopped, the exact call, and any nested run."""

    request: Request
    point: str
    call: ToolCall | None = None
    child: str | None = None


class Checkpoint(BaseModel):
    """Everything a run is, version 1.

    ``apply`` in ``recovery.py`` is the only code that changes it, one event at a time, so this
    snapshot and a rebuild from the log are equal by construction. ``action``, ``calls``,
    ``results``, ``allowed`` and ``started`` describe the open step, so a run continues inside a
    step without repeating what the log already holds. ``allowed`` holds approved call ids, and
    ``llm`` or ``finish`` for an approved pause at those points.
    """

    model_config = ConfigDict(extra="forbid")

    version: int = CHECKPOINT_VERSION
    run_id: str = ""
    root: str = ""
    parent: str | None = None
    parent_step: int | None = None
    chat: str | None = None
    project: str | None = None
    agent_class: str = ""
    agent: str = ""
    loop: str | None = None
    loop_state: dict[str, Any] = {}
    max_steps: int = 0
    settings: dict[str, Any] = {}
    messages: list[Message] = []
    step: int = 0
    in_step: bool = False
    action: Action | None = None
    calls: list[ToolCall] = []
    results: dict[str, Message] = {}
    allowed: list[str] = []
    started: list[str] = []
    usage: Usage = Usage()
    step_usage: Usage = Usage()
    pending: PendingAction | None = None
    failures: dict[str, int] = {}
    output_failures: int = 0
    has_answer: bool = False
    answer: Any = None
    status: str = "running"
    stop_reason: str | None = None
    message: str | None = None
    sequence: int = 0
    created: str = ""

    def dump(self):
        """Return the JSON form a store saves."""
        return self.model_dump(mode="json")

    @classmethod
    def load(cls, data):
        """Return the checkpoint of a JSON form; a wrong version or shape raises."""
        version = data.get("version") if isinstance(data, dict) else None
        if version != CHECKPOINT_VERSION:
            raise CheckpointError(f"checkpoint: version = {version!r}; expected 1")
        try:
            return cls.model_validate(data)
        except pydantic.ValidationError as error:
            raise CheckpointError(f"checkpoint: wrong shape: {error}") from error
