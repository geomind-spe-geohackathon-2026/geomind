"""When a conversation is too long, and which of its turns a summary replaces.

The summary itself is an LLM call, so it is made in ``engine/compaction.py``.
"""

import asyncio

from geomind import runtime
from geomind.context.history import SUMMARY_HEADING, split_turns
from geomind.errors import RunError
from geomind.types import RULE_MODEL
from geomind.utils.models import fetch_context_windows

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


_windows = None


def forget_windows():
    """Drop the windows read from the provider, for tests."""
    global _windows
    _windows = None


async def load_windows(models, fetcher=fetch_context_windows):
    """Read the provider's windows once per process, off the event loop, and check the models.

    A fake or scripted run never calls this. Raises ``RunError`` when the list cannot be read or
    lacks a model, unless the setting ``context_window`` gives the window.
    """
    global _windows
    if runtime.get("context_window") is not None:
        return
    if _windows is None:
        try:
            _windows = await asyncio.to_thread(fetcher)
        except Exception as error:
            raise RunError(
                f"compaction: context windows = unknown; the model list failed "
                f"({type(error).__name__}); set GEOMIND_CONTEXT_WINDOW"
            ) from error
    absent = sorted({model for model in models if model not in _windows})
    if absent:
        raise RunError(
            f"compaction: context window of {absent} = unknown; not in the provider's model "
            "list; set GEOMIND_CONTEXT_WINDOW"
        )


def context_window(model):
    """Return the window of a model in tokens: the setting, else the loaded provider list.

    Returns ``None`` when neither exists, which is a run with no real provider.
    """
    explicit = runtime.get("context_window")
    if explicit is not None:
        return explicit
    return (_windows or {}).get(model)


def is_over_threshold(messages, model):
    """Tell whether rendered messages pass the share of the model's window that is allowed.

    A rule agent calls no model, and a run without a window (fake or scripted) is never over.
    """
    window = None if model == RULE_MODEL else context_window(model)
    if window is None:
        return False
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
