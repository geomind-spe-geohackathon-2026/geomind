"""The protocol every LLM service implements."""

from typing import Protocol


def needs_models(llm):
    """Tell whether a provider, or the one it wraps, is real: it calls a model by id."""
    while llm is not None:
        if getattr(llm, "needs_models", False):
            return True
        llm = getattr(llm, "llm", None)
    return False


class LLM(Protocol):
    """One model call: ``on_text(delta)`` streams text, ``settings`` holds temperature and limits.

    A provider may also have ``secrets``, the known secret values to redact from every event.
    """

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Return the ``Completion`` of one call."""
