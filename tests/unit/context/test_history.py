"""Turns of a chat."""

from geomind.context import Compaction, restore
from geomind.context.history import replace_older, split_turns, summary_message
from geomind.types import Message


def message(role, content):
    """Return one message."""
    return Message(role=role, content=content)


CHAT = [
    message("system", "prompt"),
    message("user", "one"),
    message("assistant", "a"),
    message("tool", "t"),
    message("user", "two"),
    message("assistant", "b"),
]


def test_a_turn_starts_at_a_user_message_and_holds_all_that_follows():
    """Tool messages stay with their turn, so a call is never split from its result."""
    head, turns = split_turns(CHAT)
    assert [item.content for item in head] == ["prompt"]
    assert [[item.content for item in turn] for turn in turns] == [["one", "a", "t"], ["two", "b"]]


def test_a_summary_replaces_the_oldest_turns():
    """The head stays, then the summary, then the newest turns verbatim."""
    contents = [item.content for item in replace_older(CHAT, "short", 1)]
    assert contents == ["prompt", summary_message("short").content, "two", "b"]


def test_a_new_summary_replaces_the_earlier_one():
    """There is only ever one summary."""
    once = replace_older(CHAT, "first", 1)
    twice = replace_older(once, "second", 1)
    assert [item.content for item in twice] == ["prompt", summary_message("second").content]


def test_restore_without_a_compaction_is_the_history():
    """A chat that never compacted reads as it is."""
    assert restore(CHAT, None) == CHAT


def test_restore_gives_the_summary_and_the_newer_turns():
    """The next run of a chat sees what the last one left."""
    restored = restore(CHAT, Compaction(summary="short", turns=1))
    assert [item.content for item in restored][-2:] == ["two", "b"]
    assert restored[1] == summary_message("short")
