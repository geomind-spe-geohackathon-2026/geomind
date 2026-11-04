"""A scripted provider for tests, examples and replay, and what records one."""

import hashlib
import json
import re

from geomind.errors import ProviderError
from geomind.types import RULE_MODEL, Completion, Usage
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
        return cls(recorded_completion(line) for line in read_lines(path))

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
        line = completion.model_dump(mode="json", exclude={"raw"})
        append_line(self.path, {**line, INPUT_DIGEST: input_digest(messages)})
        return completion


INPUT_DIGEST = "input_digest"
"""The key of a recorded line that holds the digest of the tool results the call answered."""
RUN_ID = re.compile(r"\b[0-9a-f]{16,}\b")
"""A run, call or result id, which differs between runs and is no part of what a tool said."""


def recorded_completion(line):
    """Return the completion of one recorded line, its digest left out."""
    return Completion.model_validate(
        {key: value for key, value in line.items() if key != INPUT_DIGEST}
    )


def input_digest(messages):
    """Return the digest of the tool results a call answers, ids left out.

    The results are the tool messages after the last assistant message, so two runs that gave
    the model the same results at a step have the same digest there.
    """
    tail = []
    for message in reversed(messages):
        if message.role == "assistant":
            break
        if message.role == "tool":
            tail.append(RUN_ID.sub("<id>", message.content))
    text = json.dumps(list(reversed(tail)))
    return hashlib.sha256(text.encode()).hexdigest()


class ReplayThenLive:
    """Answer the first ``steps`` calls from a recording, then call ``llm``: a run goes on live.

    A replayed completion costs nothing (its usage is zero), so a cap counts only live calls. A
    recorded line with a digest is replayed only while the tools gave the same results as in the
    recorded run; at the first difference, and after ``steps`` calls, every call is live. The tools
    always run on the code of this process.
    """

    def __init__(self, lines, llm, steps):
        """Keep the recorded lines, the live provider and how many calls may be replayed."""
        self.lines = list(lines)
        self.llm = llm
        self.steps = steps
        self.secrets = getattr(llm, "secrets", ())
        self.replayed = 0
        self.is_live = False

    @classmethod
    def from_recording(cls, path, llm, steps):
        """Read the recording at ``path``; see the class."""
        return cls(read_lines(path), llm, steps)

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Return the next recorded completion while it applies, else the live one."""
        index = self.replayed
        line = self.lines[index] if index < min(self.steps, len(self.lines)) else None
        digest = line.get(INPUT_DIGEST) if line else None
        if line is None or (digest is not None and digest != input_digest(messages)):
            self.is_live = True
        if self.is_live:
            return await self.llm.complete(
                messages, tools, model=model, settings=settings, on_text=on_text
            )
        self.replayed += 1
        completion = recorded_completion(line).model_copy(update={"usage": Usage()})
        if on_text is not None and completion.text:
            on_text(completion.text)
        return completion
