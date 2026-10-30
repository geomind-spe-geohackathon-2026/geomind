"""A scripted provider for tests, examples and replay."""

from geomind.errors import ProviderError
from geomind.types import RULE_MODEL
from geomind.types.events import LLM_EVENTS


class FakeLLM:
    """Return scripted completions in order; an exception in the script is raised instead."""

    def __init__(self, completions):
        """Keep the script and an empty list of received calls."""
        self.completions = list(completions)
        self.calls = []

    @classmethod
    def from_events(cls, events):
        """Rebuild the script from the LLM calls of a stored run, summaries included."""
        completions = [event.completion for event in events if event.type in LLM_EVENTS]
        return cls(item for item in completions if item.model != RULE_MODEL)

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Return the next scripted completion and stream its text."""
        self.calls.append({"messages": messages, "tools": tools, "model": model})
        if len(self.calls) > len(self.completions):
            raise ProviderError(f"FakeLLM: call {len(self.calls)}; the script is exhausted")
        completion = self.completions[len(self.calls) - 1]
        if isinstance(completion, Exception):
            raise completion
        if on_text is not None and completion.text:
            on_text(completion.text)
        return completion
