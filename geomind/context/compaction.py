"""When a conversation is too long, and which of its turns a summary replaces.

The summary itself is an LLM call, so it is made in ``engine/compaction.py``.
"""

from geomind import runtime
from geomind.context.history import SUMMARY_HEADING, split_turns

DEFAULT_CONTEXT_WINDOW = 128_000
CONTEXT_WINDOWS = {
    "anthropic/claude-sonnet-5.5": 200_000,
    "anthropic/claude-haiku-5.5": 200_000,
    "anthropic/claude-opus-5.5": 200_000,
}
CHARACTERS_PER_TOKEN = 4


def estimate_tokens(messages):
    """Return the tokens of messages, at four characters per token.

    NOTE: an estimate, because a count needs the provider's tokenizer, and this one must give the
    same answer in a replay.
    """
    characters = sum(
        len(message.content) + sum(len(str(call.input)) for call in message.tool_calls)
        for message in messages
    )
    return characters // CHARACTERS_PER_TOKEN


def is_over_threshold(messages, model):
    """Tell whether rendered messages pass the share of the model's window that is allowed."""
    window = CONTEXT_WINDOWS.get(model, DEFAULT_CONTEXT_WINDOW)
    return estimate_tokens(messages) > runtime.get("compaction_threshold") * window


def older_turns(messages):
    """Return the turns a summary may replace: all but the last ``compaction_keep_turns``."""
    keep = runtime.get("compaction_keep_turns")
    _, turns = split_turns(messages)
    return turns[: max(len(turns) - keep, 0)]


def transcript(messages, turns):
    """Return the text a summarizer reads: the earlier summary, if any, then the older turns."""
    head, _ = split_turns(messages)
    earlier = [item.content for item in head if item.content.startswith(SUMMARY_HEADING)]
    lines = [f"{message.role}: {message.content}" for turn in turns for message in turn]
    return "\n".join([*earlier, *lines])
