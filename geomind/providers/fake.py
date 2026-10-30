"""A scripted provider for tests, examples and replay, and what records one."""

from geomind.errors import ProviderError
from geomind.types import RULE_MODEL, Completion
from geomind.types.events import LLM_EVENTS
from geomind.utils.json import append_line, read_lines


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

    @classmethod
    def from_recording(cls, path):
        """Rebuild the script from a recording: one completion as JSON per line."""
        return cls(Completion.model_validate(line) for line in read_lines(path))

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


class Recorder:
    """Call another provider and append each completion to a recording, for ``from_recording``.

    NOTE: ``raw`` stays out, because a recording is committed and needs only what a replay reads.
    """

    def __init__(self, llm, path):
        """Wrap a provider, whose secrets stay known to the engine."""
        self.llm = llm
        self.path = path
        self.secrets = getattr(llm, "secrets", ())

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Call the provider and record what it returned."""
        completion = await self.llm.complete(
            messages, tools, model=model, settings=settings, on_text=on_text
        )
        append_line(self.path, completion.model_dump(mode="json", exclude={"raw"}))
        return completion
