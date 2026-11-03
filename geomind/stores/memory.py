"""The shared memory of the agents: cited reference data and good past designs.

Two sections. ``knowledge`` holds reference values, each with its source: ``title``,
``publisher``, ``year``, ``page`` or ``link``, ``price_year`` and ``currency`` for money, a
``status`` (``verified``, ``secondary`` or ``placeholder``) and a ``note``. ``experience`` holds
designs that passed verification: the case's general features, the plant, the results and KPIs,
the verdict and the lessons, with the run they came from. It keeps lessons, never a project's
numbers as rules.

NOTE: a memory is a protocol like the run store: ``FileMemory`` for the command line, and a
backend gives its own through the workspace (``Workspace.memory``).
"""

import json
from pathlib import Path
from typing import Protocol

from geomind.errors import ToolError
from geomind.stores.workspace import search

SECTIONS = ("knowledge", "experience")
"""The two sections of a memory."""
CITATION = ("title", "publisher", "year")
"""What every knowledge entry must name of its source."""
LOCATION = ("page", "link")
"""Where in its source a knowledge entry is: one of them at least."""
STATUSES = ("verified", "secondary", "placeholder")
"""How far a knowledge entry was checked against its source."""
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


def checked_knowledge(entry, catalogue=False):
    """Return a knowledge entry if it names its value, unit and source, else raise.

    A value without its source is no knowledge: ``title``, ``publisher``, ``year``, a ``page``
    or a ``link``, and a ``status``; money needs its ``price_year`` and ``currency``. A
    ``placeholder`` (a value no source backs yet) is kept only from a seeded ``catalogue``, and
    needs its ``note``; a model never writes one. A catalogue's price without its price year is
    kept as the catalogue gives it, its note saying so.
    """
    if entry.get("status") == "placeholder":
        return checked_placeholder(entry, catalogue)
    missing = [key for key in ("id", "item", "value", *CITATION, "status") if not entry.get(key)]
    if not any(entry.get(key) for key in LOCATION):
        missing.append("page or link")
    if entry.get("status") and entry["status"] not in STATUSES:
        missing.append(f"status one of {', '.join(STATUSES)}")
    if (
        is_money(entry)
        and not (entry.get("price_year") and entry.get("currency"))
        and not catalogue
    ):
        missing.append("price_year and currency")
    if missing:
        raise ToolError(
            f"write_memory: a knowledge entry lacks {', '.join(missing)}; expected a cited value",
            path="entry",
        )
    return entry


def checked_placeholder(entry, catalogue):
    """Return a placeholder entry of a catalogue, or raise for one a model writes."""
    if not catalogue:
        raise ToolError(
            "write_memory: status = 'placeholder'; expected a value with its source (verified or "
            "secondary): a placeholder comes only from a seeded catalogue",
            path="entry",
        )
    missing = [key for key in ("id", "item", "note") if not entry.get(key)]
    if missing:
        raise ToolError(f"memory: a placeholder lacks {', '.join(missing)}", path="entry")
    return entry


def catalogue_entries(rows, origin):
    """Return the knowledge entries of a cost catalogue's rows, each keeping its source columns.

    A row is ``{id, group, item, value, unit, price_year, source, publisher, year, page, url,
    status, quote, note}`` and more; the currency is the unit's leading code (``EUR/m`` is EUR).
    ``origin`` names the catalogue the rows came from.
    """
    entries = []
    for row in rows:
        unit = row.get("unit") or ""
        code = unit.split("/")[0]
        entry = {
            "id": row["id"],
            "group": row.get("group") or None,
            "item": row.get("item"),
            "value": number_or_text(row.get("value")),
            "unit": unit or None,
            "price_year": number_or_text(row.get("price_year")),
            "currency": code if len(code) == 3 and code.isalpha() and code.isupper() else None,
            "title": row.get("source") or None,
            "publisher": row.get("publisher") or None,
            "year": number_or_text(row.get("year")),
            "page": row.get("page") or None,
            "link": row.get("url") or None,
            "status": row.get("status"),
            "quote": row.get("quote") or None,
            "note": row.get("note") or row.get("conversion") or None,
            "origin": origin,
        }
        if is_money(entry) and not entry["price_year"]:
            entry["note"] = "; ".join(
                filter(None, [entry["note"], "no price year in the catalogue"])
            )
        entries.append(checked_knowledge(entry, catalogue=True))
    return entries


def number_or_text(value):
    """Return a catalogue value as a number, or as its text when it is a range or a phrase."""
    if value in (None, ""):
        return None
    try:
        number = float(value)
    except ValueError:
        return value
    return int(number) if number.is_integer() and "." not in value else number


def is_money(entry):
    """Tell whether a knowledge entry is a price or a cost, by its unit or its currency."""
    unit = str(entry.get("unit") or "")
    return bool(entry.get("currency")) or any(sign in unit for sign in ("EUR", "USD", "$", "€"))


def search_knowledge(memory, query):
    """Return the knowledge entries that hold a word of ``query``, best first."""
    items = [
        {"title": "", "text": json.dumps(entry, ensure_ascii=False), "entry": entry}
        for entry in memory.entries("knowledge")
    ]
    return [{**item["entry"], "score": item["score"]} for item in search(items, query)]


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


class MemoryMemory:
    """Hold the sections in memory, for tests and for a run that keeps nothing."""

    def __init__(self, knowledge=(), experience=()):
        """Start with the entries given."""
        self.sections = {"knowledge": list(knowledge), "experience": list(experience)}

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
