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
    "study.recorded",
    "request",
    "usage",
    "run.finished",
)
INTERNAL_EVENTS = (
    "llm.completed",
    "tool.result",
    "permission",
    "retry",
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
    "save_chat_artifact",
    "load_chat_artifact",
    "load_events",
)
RESULT_FIELDS = ("run_id", "status", "answer", "request", "usage", "stop_reason", "message")


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
    """``RunStore``, ``Workspace`` and ``LLM``, as of 0.3.0; ``SandboxProvider`` left in 0.4.22.

    0.3.0 added the chat artifacts of ``RunStore`` and ``Workspace.plants``, and the files of
    ``Workspace.case``; 0.4.4 the optional ``Workspace.files`` and ``Workspace.file``; 0.4.22 the
    optional ``knowledge_search``, ``knowledge_files`` and ``knowledge_file``; 0.4.22.dev48 the
    optional ``project_state`` (contract v4); 0.4.23 the optional ``memory``.
    """
    protocols = frozen["protocols"]
    assert set(protocols["RunStore"]) == set(RUN_STORE_METHODS)
    assert set(protocols["Workspace"]) == {
        "plants",
        "rag",
        "case",
        "files",
        "file",
        "project_state",
        "knowledge_search",
        "knowledge_files",
        "knowledge_file",
        "mcp",
        "memory",
    }
    assert (
        protocols["LLM"]["complete"] == "(self, messages, tools, *, model, settings, on_text=None)"
    )
    assert "SandboxProvider" not in protocols and "Sandbox" not in protocols


def test_section_three_run_is_frozen(frozen):
    """The call the contract shows, every method included."""
    methods = frozen["Run"]
    assert {"__init__", "start", "astart", "load", "resume", "aresume", "cancel"} == set(methods)
    assert [word for word in RUN_KEYWORDS if f"{word}=" not in methods["__init__"]] == []
    missing = {"llm", "store", "workspace", "permissions", "callbacks", "hooks"}
    assert [word for word in missing if f"{word}=" not in methods["load"]] == []
    assert "sandbox=" not in methods["__init__"] and "sandbox=" not in methods["load"]


def test_section_three_result_is_frozen(frozen):
    """The fields the contract lists, ``message`` since 0.4.8."""
    fields = set(frozen["RunResult"]["properties"])
    assert set(RESULT_FIELDS) <= fields


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
