"""The knowledge base: shared documents the agents search for cited values (retrieval).

A document is cut into passages: a PDF by its ``[page n]`` pages, each page or text file into
paragraphs joined up to ``PASSAGE_CHARACTERS``. A search ranks the passages by the words of the
query they hold, rarer words counting more, so it is deterministic and needs no model. Each
passage keeps its citation: the document, its title (the first line), the page and its text.
"""

import math
import re
from pathlib import Path

from geomind.errors import ToolError
from geomind.stores.documents import document_text
from geomind.stores.workspace import file_entry, is_safe_name, read_bytes

PASSAGE_CHARACTERS = 1200
"""The longest passage a search returns, about a paragraph of a page."""
WORD = re.compile(r"[a-z0-9]+(?:\.[0-9]+)?", re.IGNORECASE)
PAGE = re.compile(r"^\[page (\d+)\]$", re.MULTILINE)


def words_of(text):
    """Return the lower-case words of a text."""
    return [word.lower() for word in WORD.findall(text)]


def pages_of(text):
    """Return ``[(page or None, text)]``: a PDF by its page markers, any other text whole."""
    marks = list(PAGE.finditer(text))
    if not marks:
        return [(None, text)]
    ends = [mark.start() for mark in marks[1:]] + [len(text)]
    return [(int(mark[1]), text[mark.end() : end]) for mark, end in zip(marks, ends)]


def pieces_of(body):
    """Return the paragraphs of a page, a paragraph longer than a passage as its lines."""
    pieces = []
    for paragraph in re.split(r"\n\s*\n", body):
        if len(paragraph) > PASSAGE_CHARACTERS:
            pieces.extend(line for line in paragraph.splitlines() if line.strip())
        else:
            pieces.append(paragraph)
    return pieces


def passages_of(name, text):
    """Return the passages of one document, each ``{id, document, title, page, text}``."""
    title = next((line.strip() for line in text.splitlines() if line.strip()), name)[:120]
    header = title if name.lower().endswith((".csv", ".tsv")) else None
    found = []
    for page, body in pages_of(text):
        held = ""
        for piece in pieces_of(body):
            if held and len(held) + len(piece) > PASSAGE_CHARACTERS:
                found.append((page, held))
                held = header or ""
            held = f"{held}\n{piece}".strip() if held else piece.strip()
        if held and held != header:
            found.append((page, held))
    return [
        {
            "id": f"{name}#{number}",
            "document": name,
            "title": title,
            "page": page,
            "text": part[: PASSAGE_CHARACTERS * 2],
        }
        for number, (page, part) in enumerate(found, start=1)
    ]


def ranked(passages, query, limit):
    """Return the passages that best hold the words of ``query``, with ``score``, best first.

    ``limit`` cuts the list; ``None`` keeps every passage that holds a word.
    """
    asked = set(words_of(query))
    if not asked:
        return []
    held = [(item, set(words_of(item["text"]))) for item in passages]
    counts = {word: sum(word in words for _, words in held) for word in asked}
    weight = {word: math.log(1 + len(held) / (1 + count)) for word, count in counts.items()}
    scored = []
    for item, words in held:
        score = sum(weight[word] for word in asked & words)
        if score > 0:
            scored.append({**item, "score": round(score, 3)})
    return sorted(scored, key=lambda item: (-item["score"], item["id"]))[:limit]


class FolderKnowledge:
    """The documents of one folder as the knowledge base: its files, their bytes and a search."""

    def __init__(self, root):
        """Remember the folder; its documents are read at the first search."""
        self.root = Path(root)
        self._passages = None

    def files(self):
        """Return ``[{name, size, media_type}]`` of every file of the folder, by its path there."""
        paths = sorted(path for path in self.root.rglob("*") if path.is_file())
        return [
            file_entry(path.relative_to(self.root).as_posix(), path.stat().st_size)
            for path in paths
        ]

    def file(self, name):
        """Return the bytes of a document, or ``None`` for a name not in the folder."""
        if not is_safe_name(name):
            return None
        return read_bytes(self.root / name)

    def passages(self):
        """Return every passage of every document that reads as text, read once."""
        if self._passages is None:
            found = []
            for entry in self.files():
                try:
                    text = document_text(entry["name"], self.file(entry["name"]))
                except ToolError:
                    continue
                found.extend(passages_of(entry["name"], text))
            self._passages = found
        return self._passages

    def search(self, query):
        """Return the passages that best answer ``query``, each with its citation and score."""
        return ranked(self.passages(), query, None)


class MemoryKnowledge(FolderKnowledge):
    """Documents held in memory, ``{name: bytes}``, for tests and a backend that has them."""

    def __init__(self, documents):
        """Keep the documents."""
        self.documents = dict(documents)
        self._passages = None

    def files(self):
        """Return the rows of the documents, by name."""
        return [file_entry(name, len(self.documents[name])) for name in sorted(self.documents)]

    def file(self, name):
        """Return the bytes of a document, or ``None``."""
        return self.documents.get(name)
