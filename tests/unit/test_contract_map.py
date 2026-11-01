"""Every code path in the contract map exists, so the map cannot go stale."""

import json
import re

import pytest

from tests.fixtures import ROOT

DOCUMENT = ROOT / ".claude/docs/contracts.md"
SNAPSHOT = ROOT / "tests/unit/snapshots/api.json"
RUN_KEYWORDS = (
    "chat",
    "project",
    "history",
    "llm",
    "store",
    "workspace",
    "sandbox",
    "permissions",
    "callbacks",
    "hooks",
)
PUBLIC_EVENTS = (
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
)
INTERNAL_EVENTS = (
    "llm.completed",
    "tool.result",
    "permission",
    "retry",
    "sandbox.provisioned",
    "sandbox.closed",
    "error",
    "compaction",
)
RUN_STORE_METHODS = (
    "save_event",
    "load_history",
    "save_state",
    "load_state",
    "save_artifact",
    "load_artifact",
    "load_events",
)
RESULT_FIELDS = ("run_id", "status", "answer", "request", "usage", "stop_reason")
KNOWN_MISSING_RESULT_FIELDS = {"message"}
"""The contract says ``RunResult.message`` and the code has none; reported to Sahand."""


@pytest.fixture(scope="module")
def frozen():
    """Return the frozen items facing the backend."""
    return json.loads(SNAPSHOT.read_text())["items"]


def test_every_mapped_path_exists():
    """Each ``geomind/``, ``tests/`` and ``examples/`` path in the tables is a real file."""
    paths = re.findall(r"`((?:geomind|tests|examples)/[\w/.]+\.py)`", DOCUMENT.read_text())
    assert len(paths) > 40
    assert [path for path in paths if not (ROOT / path).is_file()] == []


def test_section_two_events_are_frozen(frozen):
    """Every public and internal event of the contract, public as the contract says."""
    events = frozen["events"]
    assert [name for name in PUBLIC_EVENTS if not events[name]["is_public"]] == []
    assert [name for name in INTERNAL_EVENTS if events[name]["is_public"]] == []
    assert set(events) == {*PUBLIC_EVENTS, *INTERNAL_EVENTS}


def test_section_three_protocols_are_frozen(frozen):
    """``RunStore``, ``Workspace`` (with ``case`` since 0.2.0), ``LLM`` and ``SandboxProvider``."""
    protocols = frozen["protocols"]
    assert set(protocols["RunStore"]) == set(RUN_STORE_METHODS)
    assert set(protocols["Workspace"]) == {"plant", "documents", "case"}
    assert (
        protocols["LLM"]["complete"] == "(self, messages, tools, *, model, settings, on_text=None)"
    )
    assert set(protocols["SandboxProvider"]) == {"provision"}


def test_section_three_run_is_frozen(frozen):
    """The call the contract shows, every method included."""
    methods = frozen["Run"]
    assert {"__init__", "start", "astart", "load", "resume", "aresume", "cancel"} == set(methods)
    assert [word for word in RUN_KEYWORDS if f"{word}=" not in methods["__init__"]] == []
    missing = {"llm", "store", "workspace", "sandbox", "permissions", "callbacks", "hooks"}
    assert [word for word in missing if f"{word}=" not in methods["load"]] == []


def test_section_three_result_is_frozen(frozen):
    """The fields the contract lists; a missing one stays a reported difference."""
    fields = set(frozen["RunResult"]["properties"])
    assert set(RESULT_FIELDS) <= fields
    assert not KNOWN_MISSING_RESULT_FIELDS & fields


def test_section_three_statuses_are_frozen(frozen):
    """The statuses of ``run``, ``queued`` being the backend's own."""
    assert set(frozen["stop_reasons"].values()) == {"waiting", "done", "failed", "cancelled"}


def test_section_three_answers_and_hooks_are_frozen(frozen):
    """Both answer shapes, and the hooks of the contract's call."""
    schemas = frozen["answers"]["$defs"]
    assert set(schemas["Approval"]["properties"]) == {"approved", "reason"}
    assert set(schemas["Reply"]["properties"]) == {"text"}
    assert {"TokenBudget", "RequireApproval", "Cancellation"} <= set(frozen["hooks"])


def test_message_has_the_contract_fields(frozen):
    """``{role, content, tool_calls?, tool_call_id?}``, with the four roles."""
    message = frozen["Message"]["properties"]
    assert set(message) == {"role", "content", "tool_calls", "tool_call_id"}
    assert set(message["role"]["enum"]) == {"user", "assistant", "tool", "system"}
