"""The plants, case and documents of a project."""

import mimetypes
import re
from pathlib import Path
from typing import Protocol

from geomind.stores.casefiles import is_safe_name, named_files
from geomind.utils.json import read_json

WORD = re.compile(r"\w+")
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

    def rag(self, project_id, query):
        """Return matching documents as ``[{id, title, text, score}]``, best first."""

    def files(self, project_id):
        """Return the project's files as ``[{name, size, media_type}]``; ``[]`` without any.

        NOTE: optional, with ``file``. A workspace without the two keeps working: the file tools
        answer ``files_unavailable``. ``size`` is in bytes and ``media_type`` a MIME type.
        """

    def file(self, project_id, name):
        """Return the bytes of a file ``files`` lists, or ``None`` for any other name."""

    def mcp(self, project_id):
        """Return the MCP servers of a project as ``[{name, url, transport, headers}]``.

        NOTE: optional. ``name`` matches ``[a-z0-9_-]{1,32}``, ``transport`` is ``http`` or
        ``sse``, and the header values are secrets geomind never logs, stores or shows.
        """

    def project_state(self, project_id):
        """Return how far a project's work is, for the next-step suggestions, or ``None``.

        ``{case, plant, study, results, report: {state, label}, case_version, plant_version,
        study_case_version, case_changed_after_study}``; each state is ``empty``,
        ``incomplete``, ``ready``, ``running`` or ``done``. NOTE: optional (contract v4); without
        it, or with ``None``, the suggestions follow the chat's problem state.
        """

    def memory(self, project_id):
        """Return the agents' memory for a project (``entries`` and ``add``), or ``None``.

        NOTE: optional. ``None`` turns the memory off for that project: the memory tools are not
        offered and nothing is written. A workspace with this method needs no
        ``GEOMIND_MEMORY_DIR``; without it, ``GEOMIND_MEMORY`` on uses the folder store there.
        """

    def knowledge_search(self, query):
        """Return passages of the shared knowledge base, best first.

        Each passage is ``{id, document, title, page, text, score}``. NOTE: optional, with
        ``knowledge_files`` and ``knowledge_file``. A workspace without them keeps working:
        ``read_rag`` of ``knowledge/<name>`` answers ``knowledge_unavailable``.
        """

    def knowledge_files(self):
        """Return the documents of the knowledge base as ``[{name, size, media_type}]``."""

    def knowledge_file(self, name):
        """Return the bytes of a document ``knowledge_files`` lists, or ``None``."""


def file_entry(name, size):
    """Return the row of a project file: its name, size in bytes and media type."""
    media_type = mimetypes.guess_type(name)[0] or "application/octet-stream"
    return {"name": name, "size": size, "media_type": media_type}


def search(documents, query):
    """Return the documents that hold a word of ``query``, by keyword count, best first."""
    words = {word.lower() for word in WORD.findall(query)}
    found = []
    for document in documents:
        text = f"{document['title']} {document['text']}".lower()
        score = sum(1 for word in WORD.findall(text) if word in words)
        if score:
            found.append({**document, "score": score})
    return sorted(found, key=lambda item: item["score"], reverse=True)


def read_bytes(path):
    """Return the bytes of a file, or ``None`` when it does not exist."""
    return path.read_bytes() if path.is_file() else None


class MemoryWorkspace:
    """Hold ``plants``, ``cases``, ``documents`` and ``files`` by project id.

    A project's plants are ``{name: plant file dict}``; a document is ``{id, title, text}``; a
    case is ``(case dict, {file name: bytes})``; its files are ``{name: bytes}``.
    """

    def __init__(self, plants=None, documents=None, cases=None, files=None, knowledge=None, mcp=()):
        """Keep the given values; ``knowledge`` is a knowledge base, ``mcp`` the servers."""
        self.knowledge = knowledge
        self.servers = list(mcp)
        self.project_plants = dict(plants or {})
        self.cases = dict(cases or {})
        self.project_documents = dict(documents or {})
        self.project_files = dict(files or {})

    def plants(self, project_id):
        """Return the plant files of a project, ``{}`` without any."""
        return dict(self.project_plants.get(project_id, {}))

    def case(self, project_id):
        """Return the case of a project, or ``None``."""
        return self.cases.get(project_id)

    def rag(self, project_id, query):
        """Search the documents of a project."""
        return search(self.project_documents.get(project_id, ()), query)

    def files(self, project_id):
        """Return the rows of the files of a project, by name."""
        held = self.project_files.get(project_id, {})
        return [file_entry(name, len(held[name])) for name in sorted(held)]

    def file(self, project_id, name):
        """Return the bytes of a file of a project, or ``None``."""
        return self.project_files.get(project_id, {}).get(name)

    def mcp(self, project_id):
        """Return the MCP servers of every project, as ``gd.mcp.Server``."""
        return list(self.servers)

    def knowledge_search(self, query):
        """Return the knowledge base's passages for ``query``, best first; ``[]`` without one."""
        return self.knowledge.search(query) if self.knowledge is not None else []

    def knowledge_files(self):
        """Return the knowledge base's documents as ``[{name, size, media_type}]``."""
        return self.knowledge.files() if self.knowledge is not None else []

    def knowledge_file(self, name):
        """Return the bytes of a document of the knowledge base, or ``None``."""
        return self.knowledge.file(name) if self.knowledge is not None else None


class FileWorkspace:
    """Read gemini's project folder, ``<root>/<project id>/``.

    It holds ``case.json``, ``economics.json``, ``data/`` for the series, ``plants/`` for the plant
    files (``kind: plant``), the text files in ``documents/`` and the user's files in ``files/``.
    """

    def __init__(self, root, knowledge=None, mcp=()):
        """Remember the root folder, the knowledge base and the MCP servers of every project."""
        self.root = Path(root)
        self.knowledge = knowledge
        self.servers = list(mcp)

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

    def rag(self, project_id, query):
        """Search the text files of a project."""
        folder = self.root / project_id / "documents"
        paths = sorted(path for path in folder.glob("*") if path.suffix in DOCUMENT_SUFFIXES)
        items = [{"id": path.name, "title": path.stem, "text": path.read_text()} for path in paths]
        return search(items, query)

    def files(self, project_id):
        """Return the rows of every file below ``files/``, and of the files ``case.json`` names.

        A case's data files beside ``case.json`` are the project's files too, so the agents read
        the data a case points at.
        """
        folder = self.root / project_id / "files"
        paths = sorted(path for path in folder.rglob("*") if path.is_file())
        rows = [
            file_entry(path.relative_to(folder).as_posix(), path.stat().st_size) for path in paths
        ]
        listed = {row["name"] for row in rows}
        for name in self.case_file_names(project_id):
            path = self.root / project_id / name
            if name not in listed and path.is_file():
                rows.append(file_entry(name, path.stat().st_size))
        return rows

    def case_file_names(self, project_id):
        """Return the names of the files ``case.json`` names, beside it; none without one."""
        folder = self.root / project_id
        path = folder / "case.json"
        if not path.exists():
            return []
        return sorted(named_files(read_json(path), lambda name: read_bytes(folder / name)))

    def file(self, project_id, name):
        """Return the bytes of a file below ``files/`` or one ``case.json`` names; else none."""
        if not is_safe_name(name):
            return None
        found = read_bytes(self.root / project_id / "files" / name)
        if found is None and name in self.case_file_names(project_id):
            return read_bytes(self.root / project_id / name)
        return found

    def mcp(self, project_id):
        """Return the MCP servers of every project, as ``gd.mcp.Server``."""
        return list(self.servers)

    def project_state(self, project_id):
        """Return the project's state from its folder, or ``None`` for no such folder.

        A part is ``done`` when its file or folder holds something: ``case.json``, ``plants/``,
        ``studies/``, ``results/`` and ``report/``, else ``empty``. A version is the newest
        modification time of its files, in nanoseconds; the study is stale when ``case.json`` is
        newer than the newest study.
        """
        folder = self.root / project_id
        if not folder.is_dir():
            return None
        found = {
            "case": [folder / "case.json"] if (folder / "case.json").exists() else [],
            "plant": sorted((folder / "plants").glob("*.json")),
            "study": sorted((folder / "studies").glob("*")),
            "results": sorted((folder / "results").glob("*")),
            "report": sorted((folder / "report").glob("*")),
        }
        state = {name: "done" if paths else "empty" for name, paths in found.items()}
        version = {
            name: max((path.stat().st_mtime_ns for path in paths), default=None)
            for name, paths in found.items()
        }
        stale = (
            version["case"] is not None
            and version["study"] is not None
            and version["case"] > version["study"]
        )
        return {
            **{name: state[name] for name in ("case", "plant", "study", "results")},
            "report": {"state": state["report"], "label": "report"},
            "case_version": version["case"],
            "plant_version": version["plant"],
            "study_case_version": version["study"],
            "case_changed_after_study": stale,
        }

    def knowledge_search(self, query):
        """Return the knowledge base's passages for ``query``, best first; ``[]`` without one."""
        return self.knowledge.search(query) if self.knowledge is not None else []

    def knowledge_files(self):
        """Return the knowledge base's documents as ``[{name, size, media_type}]``."""
        return self.knowledge.files() if self.knowledge is not None else []

    def knowledge_file(self, name):
        """Return the bytes of a document of the knowledge base, or ``None``."""
        return self.knowledge.file(name) if self.knowledge is not None else None
