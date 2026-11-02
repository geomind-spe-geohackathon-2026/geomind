"""Where a run keeps its log, chats and artifacts."""

import copy
import re
from pathlib import Path
from typing import Protocol

from geomind.errors import RunError
from geomind.types import Message
from geomind.types.events import event_from_dict
from geomind.utils.json import append_line, read_json, read_lines, write_json

_SAFE_NAME = re.compile(r"^[\w.-]+$")
REFERENCE_KINDS = ("design", "result", "case", "module")


class RunStore(Protocol):
    """The store of the backend contract; sync, because geomind calls it from a worker thread."""

    def save_event(self, run_id, event):
        """Append one event to a run's log."""

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

    def load_events(self, run_id):
        """Return a run's events in sequence order; recovery and replay read them."""


class MemoryRunStore:
    """Keep everything in this process; ``add_message`` fills a chat's history."""

    def __init__(self):
        """Start empty."""
        self.events = {}
        self.histories = {}
        self.states = {}
        self.artifacts = {}

    def save_event(self, run_id, event):
        """Append one event to a run's log."""
        self.events.setdefault(run_id, []).append(event)

    def load_events(self, run_id):
        """Return a run's events in sequence order."""
        return list(self.events.get(run_id, ()))

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


def _safe_key(key):
    """Return an artifact key that is safe as a path: one name, or a frozen reference.

    A ``case/<file name>`` may be a path such as ``case/data/demand.csv``; each part is safe.
    """
    kind, slash, name = str(key).partition("/")
    if not (slash and kind in REFERENCE_KINDS):
        return _safe(key)
    parts = name.split("/") if kind == "case" else [name]
    return f"{kind}/" + "/".join(_safe(part) for part in parts)


class FileRunStore:
    """Keep everything in files.

    A run has ``<root>/<run id>/events.jsonl`` and ``artifacts/``; a chat has
    ``<root>/chats/<chat id>/history.jsonl`` and ``state.json``. Ids become path parts, so unsafe
    ones raise. An artifact key is one such part, or the frozen ``design/<name>``,
    ``result/<id>``, ``module/<file name>`` (an agent-written module) or ``case/<file name>``, a
    file of the run's case (its name may be a path).
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
        """Return a run's events in sequence order."""
        return [event_from_dict(line) for line in read_lines(self._run(run_id) / "events.jsonl")]

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
        stem = self._run(run_id) / "artifacts" / _safe_key(key)
        if isinstance(data, bytes):
            stem.parent.mkdir(parents=True, exist_ok=True)
            stem.with_name(f"{stem.name}.bin").write_bytes(data)
            return
        write_json(stem.with_name(f"{stem.name}.json"), data)

    def load_artifact(self, run_id, key):
        """Return an artifact, or ``None``."""
        stem = self._run(run_id) / "artifacts" / _safe_key(key)
        if stem.with_name(f"{stem.name}.bin").exists():
            return stem.with_name(f"{stem.name}.bin").read_bytes()
        path = stem.with_name(f"{stem.name}.json")
        return read_json(path) if path.exists() else None
