"""A scripted provider for tests, examples and replay."""

from swarmax.errors import ProviderError
from swarmax.types import RULE_MODEL


class FakeLLM:
    """Return scripted completions in order; an exception in the script is raised instead."""

    def __init__(self, completions):
        """Keep the script and an empty list of received calls."""
        self.completions = list(completions)
        self.calls = []

    @classmethod
    def from_events(cls, events):
        """Rebuild the script from the ``llm.completed`` events of a stored run."""
        completions = [event.completion for event in events if event.type == "llm.completed"]
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
