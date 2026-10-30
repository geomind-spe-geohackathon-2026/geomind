"""Where a run keeps its log, snapshots, chats and artifacts."""

import copy
from typing import Protocol


class RunStore(Protocol):
    """The store of the backend contract; sync, because swarmax calls it from a worker thread."""

    def save_event(self, run_id, event):
        """Append one event to a run's log."""

    def save_checkpoint(self, run_id, checkpoint):
        """Replace a run's checkpoint, a JSON-safe dictionary."""

    def load_checkpoint(self, run_id):
        """Return a run's checkpoint, or ``None``."""

    def load_history(self, chat_id):
        """Return the user and assistant messages of a chat, oldest first."""

    def save_state(self, chat_id, state):
        """Replace the problem state of a chat."""

    def load_state(self, chat_id):
        """Return the problem state of a chat, or ``None``."""

    def save_artifact(self, run_id, key, data):
        """Save bytes or a JSON value under a key."""

    def load_artifact(self, run_id, key):
        """Return an artifact, or ``None``."""


class MemoryRunStore:
    """Keep everything in this process; ``add_message`` fills a chat's history."""

    def __init__(self):
        """Start empty."""
        self.events = {}
        self.checkpoints = {}
        self.histories = {}
        self.states = {}
        self.artifacts = {}

    def save_event(self, run_id, event):
        """Append one event to a run's log."""
        self.events.setdefault(run_id, []).append(event)

    def load_events(self, run_id):
        """Return a run's events in order.

        NOTE: this is not part of the backend contract yet; see ``contracts.md``.
        """
        return list(self.events.get(run_id, ()))

    def save_checkpoint(self, run_id, checkpoint):
        """Replace a run's checkpoint."""
        self.checkpoints[run_id] = copy.deepcopy(checkpoint)

    def load_checkpoint(self, run_id):
        """Return a run's checkpoint, or ``None``."""
        return copy.deepcopy(self.checkpoints.get(run_id))

    def add_message(self, chat_id, message):
        """Append one message to a chat; the backend's own store fills history itself."""
        self.histories.setdefault(chat_id, []).append(message)

    def load_history(self, chat_id):
        """Return the messages of a chat, oldest first."""
        return list(self.histories.get(chat_id, ()))

    def save_state(self, chat_id, state):
        """Replace the problem state of a chat."""
        self.states[chat_id] = copy.deepcopy(state)

    def load_state(self, chat_id):
        """Return the problem state of a chat, or ``None``."""
        return copy.deepcopy(self.states.get(chat_id))

    def save_artifact(self, run_id, key, data):
        """Save bytes or a JSON value under a key."""
        self.artifacts[(run_id, key)] = copy.deepcopy(data)

    def load_artifact(self, run_id, key):
        """Return an artifact, or ``None``."""
        return copy.deepcopy(self.artifacts.get((run_id, key)))
