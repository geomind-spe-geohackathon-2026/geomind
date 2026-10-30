"""Where a run keeps its log, snapshots, chats and artifacts."""

import copy
import re
from pathlib import Path
from typing import Protocol

from swarmax.core.types import Message
from swarmax.core.types.events import event_from_dict
from swarmax.errors import RunError
from swarmax.utils.json import append_line, read_json, read_lines, write_json

_SAFE_NAME = re.compile(r"^[\w.-]+$")


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


def _safe(name):
    """Return an id that is safe as one path part."""
    if not _SAFE_NAME.match(str(name)) or set(str(name)) == {"."}:
        raise RunError(f"store: name = {name!r}; expected letters, digits, '.', '_' or '-'")
    return str(name)


class FileRunStore:
    """Keep everything in files.

    A run has ``<root>/<run id>/events.jsonl``, ``checkpoint.json`` and ``artifacts/``; a chat has
    ``<root>/chats/<chat id>/history.jsonl`` and ``state.json``. Ids become path parts, so unsafe
    ones raise.
    """

    def __init__(self, root=".runs"):
        """Remember the root folder."""
        self.root = Path(root)

    def _run(self, run_id):
        """Return the folder of a run."""
        return self.root / _safe(run_id)

    def _chat(self, chat_id):
        """Return the folder of a chat."""
        return self.root / "chats" / _safe(chat_id)

    def save_event(self, run_id, event):
        """Append one event to a run's log."""
        append_line(self._run(run_id) / "events.jsonl", event.to_dict())

    def load_events(self, run_id):
        """Return a run's events in order.

        NOTE: this is not part of the backend contract yet; see ``contracts.md``.
        """
        return [event_from_dict(line) for line in read_lines(self._run(run_id) / "events.jsonl")]

    def save_checkpoint(self, run_id, checkpoint):
        """Replace a run's checkpoint."""
        write_json(self._run(run_id) / "checkpoint.json", checkpoint)

    def load_checkpoint(self, run_id):
        """Return a run's checkpoint, or ``None``."""
        path = self._run(run_id) / "checkpoint.json"
        return read_json(path) if path.exists() else None

    def add_message(self, chat_id, message):
        """Append one message to a chat; the backend's own store fills history itself."""
        append_line(self._chat(chat_id) / "history.jsonl", message.model_dump(mode="json"))

    def load_history(self, chat_id):
        """Return the messages of a chat, oldest first."""
        lines = read_lines(self._chat(chat_id) / "history.jsonl")
        return [Message.model_validate(line) for line in lines]

    def save_state(self, chat_id, state):
        """Replace the problem state of a chat."""
        write_json(self._chat(chat_id) / "state.json", state)

    def load_state(self, chat_id):
        """Return the problem state of a chat, or ``None``."""
        path = self._chat(chat_id) / "state.json"
        return read_json(path) if path.exists() else None

    def save_artifact(self, run_id, key, data):
        """Save bytes as ``.bin`` or a JSON value as ``.json`` under a key."""
        folder = self._run(run_id) / "artifacts"
        if isinstance(data, bytes):
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{_safe(key)}.bin").write_bytes(data)
            return
        write_json(folder / f"{_safe(key)}.json", data)

    def load_artifact(self, run_id, key):
        """Return an artifact, or ``None``."""
        stem = self._run(run_id) / "artifacts" / _safe(key)
        if stem.with_name(f"{stem.name}.bin").exists():
            return stem.with_name(f"{stem.name}.bin").read_bytes()
        path = stem.with_name(f"{stem.name}.json")
        return read_json(path) if path.exists() else None
