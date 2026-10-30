"""The plants and documents of a project."""

import re
from pathlib import Path
from typing import Protocol

from geomind.engine.checkpoint import import_class
from geomind.utils.json import read_json

_WORD = re.compile(r"\w+")
DOCUMENT_SUFFIXES = (".md", ".txt")


class Workspace(Protocol):
    """The workspace of the backend contract; sync, called from a worker thread."""

    def plant(self, project_id):
        """Return the stored plant as a gemini plant, or ``None``."""

    def documents(self, project_id, query):
        """Return matching documents as ``[{id, title, text, score}]``, best first."""


def search(documents, query):
    """Return the documents that hold a word of ``query``, by keyword count, best first."""
    words = {word.lower() for word in _WORD.findall(query)}
    found = []
    for document in documents:
        text = f"{document['title']} {document['text']}".lower()
        score = sum(1 for word in _WORD.findall(text) if word in words)
        if score:
            found.append({**document, "score": score})
    return sorted(found, key=lambda item: item["score"], reverse=True)


class MemoryWorkspace:
    """Hold ``plants`` by project id and ``documents`` as ``{id, title, text}`` by project id."""

    def __init__(self, plants=None, documents=None):
        """Keep the given values."""
        self.plants = dict(plants or {})
        self.project_documents = dict(documents or {})

    def plant(self, project_id):
        """Return the plant of a project, or ``None``."""
        return self.plants.get(project_id)

    def documents(self, project_id, query):
        """Search the documents of a project."""
        return search(self.project_documents.get(project_id, ()), query)


class FileWorkspace:
    """Read ``<root>/<project id>/plant.json`` and the text files in ``documents/``.

    A plant file names its own class, which loads it. NOTE: gemini is imported only here, by that
    name, and only when a plant is read, because ``import geomind`` should not pay for it.
    """

    def __init__(self, root):
        """Remember the root folder."""
        self.root = Path(root)

    def plant(self, project_id):
        """Return the plant of a project, or ``None``."""
        path = self.root / project_id / "plant.json"
        if not path.exists():
            return None
        data = read_json(path)
        return import_class(data["plant_type"]).from_dict(data)

    def documents(self, project_id, query):
        """Search the text files of a project."""
        folder = self.root / project_id / "documents"
        paths = sorted(path for path in folder.glob("*") if path.suffix in DOCUMENT_SUFFIXES)
        items = [{"id": path.name, "title": path.stem, "text": path.read_text()} for path in paths]
        return search(items, query)
