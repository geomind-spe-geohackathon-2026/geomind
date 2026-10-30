"""Every event has its stable type and, when public, exactly the contract JSON."""

import re

import pydantic
import pytest

from geomind.errors import RunError
from geomind.types import Completion, Request, ToolCall, Usage
from geomind.types.events import (
    EVENT_CLASSES,
    CheckpointSaved,
    ErrorRaised,
    LLMCompleted,
    PermissionDecided,
    RequestMade,
    Retried,
    RunFinished,
    RunStarted,
    SandboxClosed,
    SandboxProvisioned,
    StateChanged,
    StepFinished,
    StepStarted,
    TextDelta,
    ToolFinished,
    ToolRecorded,
    ToolStarted,
    UsageUpdated,
    event_from_dict,
)
from tests.fixtures import ROOT

BASE = {"run_id": "r1", "sequence": 7, "time": "2026-10-30T00:00:00+00:00", "agent": "a.b"}
USAGE = Usage(input_tokens=1, output_tokens=2, cost=0.5)
USAGE_JSON = {"input_tokens": 1, "output_tokens": 2, "cost": 0.5}
REQUEST = Request(id="q1", kind="approval", message="ok?", call_id="c1")
OPTIONS = ({"value": "yes", "label": "Yes"},)
QUESTION = Request(id="q1", kind="question", message="ok?", options=OPTIONS, call_id="c1")
STARTED = dict(run="r1", loop="tool", root="r1", agent_class="a:B", max_steps=3)
ADD = {"op": "add", "path": "/requirements/-", "value": {"id": "R3", "text": "Cover peak"}}

PUBLIC_EVENTS = [
    (RunStarted(**BASE, **STARTED), {"run": "r1", "loop": "tool"}),
    (StepStarted(**BASE, index=1, model="a/b"), {"index": 1, "model": "a/b"}),
    (TextDelta(**BASE, index=1, text="hi"), {"index": 1, "text": "hi"}),
    (
        ToolStarted(**BASE, index=1, call_id="c1", tool="t", input={"x": 1}),
        {"index": 1, "call_id": "c1", "tool": "t", "input": {"x": 1}},
    ),
    (
        ToolFinished(**BASE, index=1, call_id="c1", output_summary="s", duration=0.1),
        {"index": 1, "call_id": "c1", "output_summary": "s", "duration": 0.1},
    ),
    (
        ToolFinished(**BASE, index=1, call_id="c1", output_summary="s", duration=0.1, error="e"),
        {"index": 1, "call_id": "c1", "output_summary": "s", "duration": 0.1, "error": "e"},
    ),
    (StepFinished(**BASE, index=1, usage=USAGE), {"index": 1, "usage": USAGE_JSON}),
    (StateChanged(**BASE, version=4, changes=(ADD,)), {"version": 4, "changes": [ADD]}),
    (
        RequestMade(**BASE, request=REQUEST, point="tool"),
        {"request": "q1", "call_id": "c1", "kind": "approval", "message": "ok?"},
    ),
    (
        RequestMade(**BASE, request=QUESTION, point="tool"),
        {
            "request": "q1",
            "call_id": "c1",
            "kind": "question",
            "message": "ok?",
            "options": [{"value": "yes", "label": "Yes"}],
        },
    ),
    (
        RequestMade(**BASE, request=Request(id="q", kind="question", message="m"), point="tool"),
        {"request": "q", "kind": "question", "message": "m"},
    ),
    (UsageUpdated(**BASE, **USAGE_JSON), USAGE_JSON),
    (
        RunFinished(**BASE, status="done", stop_reason="answer"),
        {"status": "done", "stop_reason": "answer"},
    ),
    (
        RunFinished(**BASE, status="failed", stop_reason="denied", message="m"),
        {"status": "failed", "stop_reason": "denied", "message": "m"},
    ),
]
INTERNAL_EVENTS = [
    LLMCompleted(**BASE, index=1, completion=Completion(text="t", usage=USAGE)),
    ToolRecorded(**BASE, index=1, call_id="c1", tool="t", output={"a": 1}),
    PermissionDecided(**BASE, index=1, decision="allow", rule="mode:auto"),
    Retried(**BASE, attempt=1, model="m", error="busy", delay=0.5),
    SandboxProvisioned(**BASE, provider="LocalSandbox"),
    SandboxClosed(**BASE),
    CheckpointSaved(**BASE, index=1),
    ErrorRaised(**BASE, error_class="ValueError", message="m", where="callback"),
]
CONTRACT_TYPES = {
    "run.started",
    "step.started",
    "text.delta",
    "tool.started",
    "tool.finished",
    "step.finished",
    "state.changed",
    "request",
    "usage",
    "run.finished",
}


@pytest.mark.parametrize(
    ("event", "expected"), PUBLIC_EVENTS, ids=lambda item: getattr(item, "type", "")
)
def test_public_data_is_exactly_the_contract_json(event, expected):
    """``data()`` carries the table's fields, plus ``agent`` and ``parent`` on every event."""
    assert event.is_public
    assert event.data() == {**expected, "agent": "a.b", "parent": None}


@pytest.mark.parametrize("event", INTERNAL_EVENTS, ids=lambda item: item.type)
def test_internal_events_are_not_public(event):
    """Internal events are stored but never streamed."""
    assert not event.is_public and "agent" in event.data()


@pytest.mark.parametrize(
    "event", [item for item, _ in PUBLIC_EVENTS] + INTERNAL_EVENTS, ids=lambda item: item.type
)
def test_every_event_survives_the_store(event):
    """``to_dict`` and ``event_from_dict`` are exact, including what ``data()`` leaves out."""
    assert event_from_dict(event.to_dict()) == event


def test_public_types_are_the_ten_of_the_contract():
    """No public type is added or lost."""
    public = {name for name, event in EVENT_CLASSES.items() if event.is_public}
    assert public == CONTRACT_TYPES


def test_contract_table_lists_the_same_types():
    """The test table matches the table of the shared document, when it is present."""
    document = ROOT.parent / "docs/contracts.md"
    if not document.exists():
        pytest.skip("the shared docs folder is a sibling of this repository")
    section = document.read_text().split("## 2. Live run events")[1].split("## 3.")[0]
    assert set(re.findall(r"^\| `([a-z.]+)` \|", section, re.MULTILINE)) == CONTRACT_TYPES


def table_fields():
    """Return ``{type: (required fields, optional fields)}`` from the shared document."""
    document = ROOT.parent / "docs/contracts.md"
    if not document.exists():
        pytest.skip("the shared docs folder is a sibling of this repository")
    section = document.read_text().split("## 2. Live run events")[1].split("**Problem state")[0]
    fields = {}
    for kind, data in re.findall(r"^\| `([a-z.]+)` \| `\{([^}]*)\}`", section, re.MULTILINE):
        names = [name.strip() for name in data.split(",")]
        required = {name for name in names if not name.endswith("?")}
        fields[kind] = (required, {name.rstrip("?") for name in names} - required)
    return fields


@pytest.mark.parametrize(
    ("event", "expected"), PUBLIC_EVENTS, ids=lambda item: getattr(item, "type", "")
)
def test_public_data_fits_the_table_of_the_contract(event, expected):
    """Every row of the shared table holds for the JSON pinned above."""
    required, optional = table_fields()[event.type]
    assert required <= set(expected) <= required | optional


@pytest.mark.parametrize(
    "changes",
    [({"op": "move", "path": "/goal"},), ({"op": "add", "path": "/other", "value": 1},)],
)
def test_state_changed_refuses_other_operations(changes):
    """The event validates its operations."""
    with pytest.raises(pydantic.ValidationError):
        StateChanged(**BASE, version=1, changes=changes)


def test_state_version_starts_at_one():
    """Version 0 does not exist."""
    with pytest.raises(pydantic.ValidationError):
        StateChanged(**BASE, version=0, changes=())


def test_a_step_stored_without_a_model_still_loads():
    """Runs stored by S1 have no ``model``, and their JSON leaves it out."""
    event = event_from_dict({"type": "step.started", "run_id": "r", "index": 1})
    assert event.data() == {"index": 1, "agent": "", "parent": None}


def test_a_request_keeps_its_pending_call():
    """The pending action is in the log though the browser never sees it."""
    event = RequestMade(**BASE, request=REQUEST, point="tool", call=ToolCall(id="c1", name="t"))
    assert event_from_dict(event.to_dict()).call.name == "t"


def test_an_unknown_type_is_refused():
    """A stored event of an unknown type raises."""
    with pytest.raises(RunError, match="event type"):
        event_from_dict({"type": "nope"})
