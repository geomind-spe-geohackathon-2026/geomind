"""The plants, case and documents of a project."""

import re
from pathlib import Path
from typing import Protocol

from geomind.stores.casefiles import named_files
from geomind.utils.json import read_json

_WORD = re.compile(r"\w+")
DOCUMENT_SUFFIXES = (".md", ".txt")


class Workspace(Protocol):
    """The workspace of the backend contract; sync, called from a worker thread."""

    def plants(self, project_id):
        """Return the project's plant files as ``{name: plant file dict}``; ``{}`` without any.

        The name is the file stem and the dict the content of the file (``kind: plant``), as
        written; ``gm.Plant.from_dict`` builds it.
        """

    def case(self, project_id):
        """Return the project's case as ``(case dict, {name: bytes})``, or ``None``.

        The dict is the content of a ``case.json``, as written. The files are every file the case
        names, such as ``data/demand.csv`` and ``economics.json``, by their path in the project.
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


def read_bytes(path):
    """Return the bytes of a file, or ``None`` when it does not exist."""
    return path.read_bytes() if path.is_file() else None


class MemoryWorkspace:
    """Hold ``plants``, ``cases`` and ``documents`` by project id.

    A project's plants are ``{name: plant file dict}``; a document is ``{id, title, text}``; a
    case is ``(case dict, {file name: bytes})``.
    """

    def __init__(self, plants=None, documents=None, cases=None):
        """Keep the given values."""
        self.project_plants = dict(plants or {})
        self.cases = dict(cases or {})
        self.project_documents = dict(documents or {})

    def plants(self, project_id):
        """Return the plant files of a project, ``{}`` without any."""
        return dict(self.project_plants.get(project_id, {}))

    def case(self, project_id):
        """Return the case of a project, or ``None``."""
        return self.cases.get(project_id)

    def documents(self, project_id, query):
        """Search the documents of a project."""
        return search(self.project_documents.get(project_id, ()), query)


class FileWorkspace:
    """Read gemini's project folder, ``<root>/<project id>/``.

    It holds ``case.json``, ``economics.json``, ``data/`` for the series, ``plants/`` for the plant
    files (``kind: plant``) and the text files in ``documents/``.
    """

    def __init__(self, root):
        """Remember the root folder."""
        self.root = Path(root)

    def plants(self, project_id):
        """Return ``{file stem: plant file dict}`` of ``plants/*.json``, ``{}`` without any."""
        paths = sorted((self.root / project_id / "plants").glob("*.json"))
        return {path.stem: read_json(path) for path in paths}

    def case(self, project_id):
        """Return ``(case dict, {name: bytes})`` from ``case.json``, or ``None`` without it."""
        folder = self.root / project_id
        path = folder / "case.json"
        if not path.exists():
            return None
        data = read_json(path)
        return data, named_files(data, lambda name: read_bytes(folder / name))

    def documents(self, project_id, query):
        """Search the text files of a project."""
        folder = self.root / project_id / "documents"
        paths = sorted(path for path in folder.glob("*") if path.suffix in DOCUMENT_SUFFIXES)
        items = [{"id": path.name, "title": path.stem, "text": path.read_text()} for path in paths]
        return search(items, query)
