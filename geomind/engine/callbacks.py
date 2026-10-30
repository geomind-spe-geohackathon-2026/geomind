"""Observers of a run, and a JSON-lines event log."""

import inspect
from pathlib import Path

from geomind.utils.json import append_line

CALLBACK_METHODS = {
    "run.started": "on_run_start",
    "step.started": "on_step_start",
    "llm.completed": "on_llm_call",
    "text.delta": "on_text",
    "tool.started": "on_tool_start",
    "tool.finished": "on_tool_end",
    "permission": "on_permission",
    "state.changed": "on_state_change",
    "request": "on_request",
    "step.finished": "on_step_end",
    "error": "on_error",
    "run.finished": "on_run_end",
}


async def call_maybe_async(function, *args):
    """Call a plain or ``async`` function and return its result."""
    result = function(*args)
    return await result if inspect.isawaitable(result) else result


class Callback:
    """Override any method, plain or ``async``; each receives the engine and one event.

    Callbacks observe only: an exception in one is an ``on_error`` event and never changes the run.
    ``on_event`` receives every event, public or internal, so the backend's publisher overrides
    only that one and forwards ``event.is_public`` events.
    """

    def on_event(self, engine, event):
        """Observe every event, before the method of its type."""

    def on_run_start(self, engine, event):
        """Observe the start of a run."""

    def on_step_start(self, engine, event):
        """Observe the start of a step."""

    def on_llm_call(self, engine, event):
        """Observe a logged completion."""

    def on_text(self, engine, event):
        """Observe a piece of streamed text."""

    def on_tool_start(self, engine, event):
        """Observe the start of a tool call."""

    def on_tool_end(self, engine, event):
        """Observe the end of a tool call."""

    def on_permission(self, engine, event):
        """Observe a permission decision."""

    def on_state_change(self, engine, event):
        """Observe a change of the problem state."""

    def on_request(self, engine, event):
        """Observe a pause; the checkpoint is already saved."""

    def on_step_end(self, engine, event):
        """Observe the end of a step."""

    def on_error(self, engine, event):
        """Observe an error the run survived or ended with."""

    def on_run_end(self, engine, event):
        """Observe the end of a run."""


class EventLog(Callback):
    """Append every event to a JSON-lines file, or keep them in memory without a path."""

    def __init__(self, path=None):
        """Create the sink."""
        self.path = Path(path) if path is not None else None
        self.events = []

    def on_event(self, engine, event):
        """Record one event."""
        if self.path is None:
            self.events.append(event)
            return
        append_line(self.path, event.to_dict())
