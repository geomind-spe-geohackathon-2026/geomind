"""The messages of a chat as turns: a turn starts at a user message."""

from geomind.types import Message

SUMMARY_HEADING = "Summary of the earlier conversation:"


def split_turns(messages):
    """Return what comes before the first user message, and the turns."""
    head = []
    turns = []
    for message in messages:
        if message.role == "user":
            turns.append([message])
        elif turns:
            turns[-1].append(message)
        else:
            head.append(message)
    return head, turns


def summary_message(summary):
    """Return the one message that stands for older turns."""
    return Message(role="system", content=f"{SUMMARY_HEADING}\n{summary}")


def replace_older(messages, summary, turn_count):
    """Return the messages with the first ``turn_count`` turns replaced by one summary.

    An earlier summary is in the head; the new one covers it, so it goes.
    """
    head, turns = split_turns(messages)
    kept = [item for item in head if not item.content.startswith(SUMMARY_HEADING)]
    recent = [message for turn in turns[turn_count:] for message in turn]
    return [*kept, summary_message(summary), *recent]


def restore(history, compaction):
    """Return a chat's history as the last run left it: summary first, newest turns verbatim."""
    if compaction is None:
        return list(history)
    return replace_older(history, compaction.summary, compaction.turns)
