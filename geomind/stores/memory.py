"""The shared memory of the agents: experience, never cited values (those are knowledge).

One section, ``experience``: designs that passed gemini's check and the reviewer, written by code
(the case's general features, the plant, the results and KPIs, the verdict, the lessons, the run
and the project they came from), and the curator's lessons and the user's facts, each with its
origin. It keeps lessons, never a project's numbers as rules. Cited values and documents are the
knowledge base (``geomind/stores/knowledge.py``), not memory.

NOTE: a memory is a protocol like the run store: ``FileMemory`` for the command line, and a
backend gives its own through the workspace (``Workspace.memory``).
"""

import json
from pathlib import Path
from typing import Protocol

from geomind.errors import ToolError

SECTIONS = ("experience",)
"""The sections of a memory: experience only; cited values are in the knowledge base."""
FEATURES = (
    "heating_peak",
    "heating_mean",
    "cooling_peak",
    "cooling_mean",
    "heating_supply",
    "cooling_supply",
    "depth",
    "step",
)
"""The general features of a case an experience entry is compared by, all in SI units."""


class Memory(Protocol):
    """Where the agents keep what outlives a run."""

    def entries(self, section):
        """Return the entries of one section, in the order they were written."""

    def add(self, section, entry):
        """Keep one entry; an entry with the id of another replaces it."""


def checked_section(section):
    """Return ``section`` if it is one of the memory's, else raise ``unknown_name``."""
    if section not in SECTIONS:
        raise ToolError(
            f"memory: section = {section!r}; expected one of {', '.join(SECTIONS)}",
            code="unknown_name",
            path="section",
        )
    return section


def similarity(first, second):
    """Return how alike two cases are, 0 to 1, over the features both have.

    Each feature counts ``1 - |a - b| / max(|a|, |b|)``; a feature only one case has counts 0, so
    a case with cooling and one without are far apart.
    """
    keys = [key for key in FEATURES if first.get(key) is not None or second.get(key) is not None]
    if not keys:
        return 0.0
    total = 0.0
    for key in keys:
        a, b = first.get(key), second.get(key)
        if a is None or b is None:
            continue
        largest = max(abs(a), abs(b))
        total += 1.0 if largest == 0 else max(0.0, 1.0 - abs(a - b) / largest)
    return total / len(keys)


LESSON_KINDS = ("lesson", "user_fact")
"""The experience entries that are no design: a role's general lesson, or a fact the user gave."""


def checked_lesson(entry):
    """Return a lesson or a user fact if it is general and says where it came from, else raise.

    A ``lesson`` names its ``role`` (an agent's snake name, or ``all``) and its ``text``, and holds
    no digit: a project's numbers are never stored as a rule. A ``user_fact`` is what the user
    said, as they said it. Both name their ``origin`` ``{run, source}``, ``source`` being ``user``
    for a user fact.
    """
    missing = [key for key in ("id", "kind", "role", "text", "origin") if not entry.get(key)]
    if missing:
        raise ToolError(f"memory: experience entry lacks {', '.join(missing)}", path=missing[0])
    if entry["kind"] not in LESSON_KINDS:
        raise ToolError(
            f"memory: kind = {entry['kind']!r}; expected one of {', '.join(LESSON_KINDS)}",
            path="kind",
        )
    if entry["kind"] == "lesson" and any(character.isdigit() for character in entry["text"]):
        raise ToolError(
            "memory: a lesson holds no number; write the method, never a project's values",
            path="text",
        )
    return entry


def lessons_for(memory, role):
    """Return the lessons of ``role`` and of every role, and the user's facts, in order."""
    return [
        entry
        for entry in memory.entries("experience")
        if entry.get("kind") == "user_fact"
        or (entry.get("kind") == "lesson" and entry.get("role") in (role, "all"))
    ]


def search_experience(memory, features, threshold):
    """Return the past designs at least ``threshold`` alike to ``features``, best first."""
    found = []
    for entry in memory.entries("experience"):
        if entry.get("kind") in LESSON_KINDS:
            continue
        score = similarity(features, entry.get("features") or {})
        if score >= threshold:
            found.append({**entry, "similarity": round(score, 3)})
    return sorted(found, key=lambda item: item["similarity"], reverse=True)


def has_memory(workspace):
    """Return whether a workspace gives the memory itself (``Workspace.memory``, optional)."""
    return callable(getattr(workspace, "memory", None))


class MemoryMemory:
    """Hold the sections in memory, for tests and for a run that keeps nothing."""

    def __init__(self, experience=()):
        """Start with the entries given."""
        self.sections = {"experience": list(experience)}

    def entries(self, section):
        """Return the entries of one section."""
        return list(self.sections[checked_section(section)])

    def add(self, section, entry):
        """Keep one entry, replacing one of the same id."""
        items = self.sections[checked_section(section)]
        items[:] = [item for item in items if item.get("id") != entry.get("id")] + [entry]


class FileMemory:
    """Keep each section as a JSON lines file, ``<root>/<section>.jsonl``."""

    def __init__(self, root):
        """Remember the folder; it is made at the first write."""
        self.root = Path(root)

    def _path(self, section):
        """Return the file of one section."""
        return self.root / f"{checked_section(section)}.jsonl"

    def entries(self, section):
        """Return the entries of one section, the last write of each id."""
        path = self._path(section)
        if not path.is_file():
            return []
        kept = {}
        for line in path.read_text().splitlines():
            if line.strip():
                entry = json.loads(line)
                kept.pop(entry.get("id"), None)
                kept[entry.get("id")] = entry
        return list(kept.values())

    def add(self, section, entry):
        """Append one entry; a later line of the same id replaces an earlier one."""
        path = self._path(section)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as file:
            file.write(json.dumps(entry, ensure_ascii=False) + "\n")
