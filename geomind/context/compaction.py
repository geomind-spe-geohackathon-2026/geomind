"""When a conversation is too long, and which of its turns a summary replaces.

The summary itself is an LLM call, so it is made in ``engine/compaction.py``.
"""

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


def context_window(model, fetcher=fetch_context_windows):
    """Return the context window of a model in tokens, or raise ``RunError``.

    The setting ``context_window`` wins; else the provider's model list, read once per call of a
    model with ``fetcher``. geomind keeps no table and makes no guess.
    """
    explicit = runtime.get("context_window")
    if explicit is not None:
        return explicit
    try:
        found = fetcher().get(model)
    except Exception as error:
        raise RunError(
            f"compaction: context window of {model!r} = unknown; the model list failed "
            f"({type(error).__name__}); set GEOMIND_CONTEXT_WINDOW"
        ) from error
    if found is None:
        raise RunError(
            f"compaction: context window of {model!r} = unknown; not in the provider's model "
            "list; set GEOMIND_CONTEXT_WINDOW"
        )
    return found


def is_over_threshold(messages, model, fetcher=fetch_context_windows):
    """Tell whether rendered messages pass the share of the model's window that is allowed.

    A rule agent calls no model, and a fake run without a model has no window unless the setting
    gives one; neither is ever over.
    """
    if model == RULE_MODEL or (model is None and runtime.get("context_window") is None):
        return False
    window = context_window(model, fetcher)
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
