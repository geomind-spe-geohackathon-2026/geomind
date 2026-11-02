"""When to compact, and what."""

import pytest

from geomind import runtime
from geomind.context.compaction import (
    estimate_tokens,
    forget_windows,
    is_over_threshold,
    load_windows,
    older_turns,
    transcript,
)
from geomind.context.history import summary_message
from geomind.errors import RunError
from geomind.types import Message, ToolCall


def text(role, content):
    """Return one message."""
    return Message(role=role, content=content)


def chat(count):
    """Return ``count`` turns."""
    return [item for n in range(count) for item in (text("user", f"q{n}"), text("assistant", "a"))]


def test_tokens_are_four_characters_each_and_count_tool_inputs():
    """The input of a call takes room too."""
    call = ToolCall(id="c", name="n", input={"a": 1})
    assert estimate_tokens([text("user", "x" * 40)]) == 10
    assert estimate_tokens([Message(role="assistant", tool_calls=(call,))]) == len("{'a': 1}") // 4


def test_the_threshold_is_a_share_of_the_explicit_window():
    """The setting gives the window; no model table exists."""
    limit = int(0.6 * 128_000)
    assert not is_over_threshold([text("user", "x" * (limit * 4))], "any/model")
    assert is_over_threshold([text("user", "x" * ((limit + 1) * 4))], "any/model")


async def test_the_window_comes_from_the_provider_list_once(monkeypatch):
    """With no setting, one fetch fills every model; two loads fetch once."""
    monkeypatch.delenv("GEOMIND_CONTEXT_WINDOW")
    fetches = []

    def fetcher():
        fetches.append(1)
        return {"a/b": 1000}

    await load_windows({"a/b"}, fetcher)
    await load_windows({"a/b"}, fetcher)
    assert len(fetches) == 1
    assert is_over_threshold([text("user", "x" * 4000)], "a/b")


async def test_an_unknown_window_is_an_error_not_a_guess(monkeypatch):
    """A model the list lacks, or a list that fails, raises and names the setting."""
    monkeypatch.delenv("GEOMIND_CONTEXT_WINDOW")
    with pytest.raises(RunError, match="GEOMIND_CONTEXT_WINDOW"):
        await load_windows({"a/b"}, lambda: {})
    forget_windows()

    def broken():
        raise OSError("no network")

    with pytest.raises(RunError, match="OSError"):
        await load_windows({"a/b"}, broken)


def test_the_threshold_is_a_setting():
    """A lower share compacts earlier."""
    with runtime.settings(compaction_threshold=0.0):
        assert is_over_threshold([text("user", "x" * 4)], "unknown/model")


def test_the_last_turns_are_never_older():
    """The default keeps six turns; fewer leave nothing to replace."""
    assert older_turns(chat(6)) == []
    assert [turn[0].content for turn in older_turns(chat(8))] == ["q0", "q1"]


def test_keep_turns_is_a_setting():
    """Keeping one turn offers all the others."""
    with runtime.settings(compaction_keep_turns=1):
        assert len(older_turns(chat(3))) == 2


def test_a_transcript_starts_with_the_earlier_summary():
    """A new summary is written from the old one and the turns."""
    messages = [summary_message("old facts"), *chat(1)]
    lines = transcript(messages, older_turns([*messages, *chat(6)])).splitlines()
    assert lines[1] == "old facts"
    assert lines[2:4] == ["user: q0", "assistant: a"]


def test_a_rule_agent_and_a_modelless_fake_run_are_never_over(monkeypatch):
    """No model, no window to compare with."""
    monkeypatch.delenv("GEOMIND_CONTEXT_WINDOW")
    assert not is_over_threshold([text("user", "x" * 10**7)], "rule")
    assert not is_over_threshold([text("user", "x" * 10**7)], "a/b")
