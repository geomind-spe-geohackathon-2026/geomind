"""When to compact, and what."""

from geomind import runtime
from geomind.context.compaction import (
    DEFAULT_CONTEXT_WINDOW,
    estimate_tokens,
    is_over_threshold,
    older_turns,
    transcript,
)
from geomind.context.history import summary_message
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


def test_the_threshold_is_a_share_of_the_window_of_the_model():
    """A known model has its own window, any other the safe default."""
    limit = int(0.6 * DEFAULT_CONTEXT_WINDOW)
    assert not is_over_threshold([text("user", "x" * (limit * 4))], "unknown/model")
    assert is_over_threshold([text("user", "x" * ((limit + 1) * 4))], "unknown/model")
    assert not is_over_threshold(
        [text("user", "x" * ((limit + 1) * 4))], "anthropic/claude-sonnet-5.5"
    )


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
