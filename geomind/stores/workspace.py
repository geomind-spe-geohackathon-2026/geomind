"""The plants, case and documents of a project."""

import re
from pathlib import Path
from typing import Protocol

from geomind.utils.json import read_json

_WORD = re.compile(r"\w+")
DOCUMENT_SUFFIXES = (".md", ".txt")


class Workspace(Protocol):
    """The workspace of the backend contract; sync, called from a worker thread."""

    def plant(self, project_id):
        """Return the stored plant as a gemini plant, or ``None``."""

    def case(self, project_id):
        """Return the project's case as ``(case dict, folder of its files)``, or ``None``.

        The dict is the content of a ``case.json``, as written; the folder holds the files it names.
        """

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
    """Hold ``plants``, ``cases`` and ``documents`` by project id.

    A document is ``{id, title, text}``; a case is ``(case dict, folder of its files)``.
    """

    def __init__(self, plants=None, documents=None, cases=None):
        """Keep the given values."""
        self.plants = dict(plants or {})
        self.cases = dict(cases or {})
        self.project_documents = dict(documents or {})

    def plant(self, project_id):
        """Return the plant of a project, or ``None``."""
        return self.plants.get(project_id)

    def case(self, project_id):
        """Return the case of a project, or ``None``."""
        return self.cases.get(project_id)

    def documents(self, project_id, query):
        """Search the documents of a project."""
        return search(self.project_documents.get(project_id, ()), query)


class FileWorkspace:
    """Read ``<root>/<project id>/plant.json``, ``case.json`` and the text files in ``documents/``.

    A plant file is gemini's ``plant.json``. NOTE: gemini is imported only here, and only when a
    plant is read, because ``import geomind`` should not pay for it.
    """

    def __init__(self, root):
        """Remember the root folder."""
        self.root = Path(root)

    def plant(self, project_id):
        """Return the plant of a project, or ``None``."""
        path = self.root / project_id / "plant.json"
        if not path.exists():
            return None
        import gemini as gm

        return gm.Plant.from_json(path)

    def case(self, project_id):
        """Return ``(case dict, project folder)`` from ``case.json``, or ``None`` without it."""
        folder = self.root / project_id
        path = folder / "case.json"
        return (read_json(path), folder) if path.exists() else None

    def documents(self, project_id, query):
        """Search the text files of a project."""
        folder = self.root / project_id / "documents"
        paths = sorted(path for path in folder.glob("*") if path.suffix in DOCUMENT_SUFFIXES)
        items = [{"id": path.name, "title": path.stem, "text": path.read_text()} for path in paths]
        return search(items, query)
