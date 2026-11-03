"""The tools over a project's results and documents."""

import re
from pathlib import Path

from geomind.errors import ToolError
from geomind.stores.workspace import WORD, search
from geomind.tools.base import tool
from geomind.tools.files import TABLE_SUFFIXES, document_text
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.runs import parse_time
from geomind.tools.gemini.stored import load_run
from geomind.tools.knowledge import PREFIX, has_knowledge

READ_UNITS = {
    "power": "MW",
    "temperature": "degC",
    "pressure": "bar",
    "volume_flow": "m3/h",
    "mass_flow": "kg/s",
}
"""The units in which the model reads a stored result: gemini's family keys for ``units=``."""


PASSAGE_CHARACTERS = 1500
"""The characters of one passage of a project file that ``search_rag`` returns."""
SHOWN_MATCHES = 8
"""The most matches ``search_rag`` returns, best first."""
NO_MATCH = (
    "no file or document of the project and no document of the knowledge base has these words, "
    "so none states this: for a value of the case, try an MCP tool when one is offered, then ask "
    "the user for it; for a design choice, choose and record it as an assumption with its "
    "reason. Another wording finds nothing more"
)
SEARCHED = "already searched in this run with the same words:"
PAGE_MARKER = re.compile(r"\[page (\d+)\]")


@tool(effect="read", late_schemas={"reference": reference_schema("result")})
def read_result(
    context,
    reference: str,
    path: str | None = None,
    field: str | None = None,
    start: str | None = None,
    end: str | None = None,
):
    """Return one series of a stored run, or a summary of the run or of one module path.

    ``reference`` is what simulate returned. With ``path`` and ``field`` it returns the series
    ``{time, value, unit}``; ``start`` and ``end`` are ISO 8601 times, both inclusive. With only
    ``path`` it returns min, max and mean of each field of that module, and with neither of the
    whole run. Power is in MW, temperature in degC, pressure in bar, flows in m3/h or kg/s.
    """
    if path is None and field is not None:
        raise ToolError(f"read_result: field = {field!r}; expected a path too", path="path")
    _, _, results = load_run(context, reference, "read_result")
    if field is None:
        return results.summary(path=path, units=READ_UNITS)
    first, last = parse_time(start, "start", "read_result"), parse_time(end, "end", "read_result")
    return results.get(path, field, start=first, end=last, units=READ_UNITS)


@tool(effect="read", keeps_result=True)
def search_rag(context, query: str):
    """Search the project's documents and files and the knowledge base; return ``{matches, note}``.

    Each match has ``scope`` (``project`` or ``knowledge``), ``text``, ``score`` and ``citation``,
    what a value taken from it is cited with. A project document: ``id`` and ``title``; a passage
    of a project file that reads as text, such as a PDF: ``name`` and ``start`` for ``read_rag``,
    cited with its ``file`` and ``page``; a passage of the knowledge base: ``name`` as
    ``knowledge/<document>`` for ``read_rag``, cited with its ``document``, ``title`` and
    ``page``. The best of each scope come first, in turn. A file's name alone matches nothing. No
    match means neither states these words, and the ``note`` says what to do instead; the same
    words again are noted too. A value from the knowledge base goes into the case only after the
    user confirms it, as any value no project file gives.
    """
    project = project_matches(context, query)
    knowledge = knowledge_matches(context, query)
    if project is None and knowledge is None:
        raise ToolError(
            "search_rag: this run has no project and no knowledge base; work from the case and "
            "the user",
            code="not_allowed",
        )
    matches = in_turn(project or [], knowledge or [])[:SHOWN_MATCHES]
    result = {"matches": matches}
    words = frozenset(word.lower() for word in WORD.findall(query))
    searched = searches_of(context)
    note = [NO_MATCH] if not matches else []
    if searched is not None and words in searched:
        note.insert(0, SEARCHED)
    if searched is not None:
        searched.add(words)
    return {**result, "note": " ".join(note)} if note else result


def in_turn(first, second):
    """Return the items of two ranked lists in turn, best of each first: their scores differ."""
    merged = []
    for index in range(max(len(first), len(second))):
        merged += [items[index] for items in (first, second) if index < len(items)]
    return merged


def project_matches(context, query):
    """Return the project's matches, best first, or ``None`` for a run without a project."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        return None
    documents = [
        {"scope": "project", **item, "citation": {"document": item["id"], "title": item["title"]}}
        for item in workspace.rag(context.project, query)
    ]
    files = [
        {
            "scope": "project",
            "name": item["name"],
            "start": item["start"],
            "text": item["text"],
            "score": item["score"],
            "citation": {"file": item["name"], "page": item["page"]},
        }
        for item in search(file_passages(context), query)
    ]
    return sorted(documents + files, key=lambda item: item["score"], reverse=True)


def knowledge_matches(context, query):
    """Return the knowledge base's passages, best first, or ``None`` for a run without one."""
    workspace = context.session.workspace
    if not has_knowledge(workspace) or not workspace.knowledge_files():
        return None
    return [
        {
            "scope": "knowledge",
            "name": f"{PREFIX}{item['document']}",
            "text": item["text"],
            "score": item["score"],
            "citation": {key: item[key] for key in ("document", "title", "page")},
        }
        for item in list(workspace.knowledge_search(query))[:SHOWN_MATCHES]
    ]


def page_at(text, position):
    """Return the number of the ``[page n]`` marker at or before ``position``, else ``None``."""
    markers = PAGE_MARKER.findall(text[: position + len("[page 0000]")])
    return int(markers[-1]) if markers else None


def searches_of(context):
    """Return the word sets the run tree searched, kept on its root session, or ``None``."""
    session = getattr(context.session, "root_session", context.session)
    return getattr(session, "searches", None)


def file_passages(context):
    """Return the passages of the project's files that read as text, ``PASSAGE_CHARACTERS`` each.

    A passage is ``{name, start, title, text, page}`` with an empty ``title``, so the file name is
    no match; ``page`` is that of the PDF page the passage starts on, ``None`` for a file without
    pages. A table (CSV, TSV) holds data, not text to search: ``read_rag`` shows its columns.
    """
    workspace = context.session.workspace
    files = workspace.files(context.project) if hasattr(workspace, "files") else []
    passages = []
    for entry in files:
        if Path(entry["name"]).suffix.lower() in TABLE_SUFFIXES:
            continue
        try:
            text = document_text(entry["name"], workspace.file(context.project, entry["name"]))
        except ToolError:
            continue
        for start in range(0, len(text), PASSAGE_CHARACTERS):
            passage = text[start : start + PASSAGE_CHARACTERS]
            page = page_at(text, start + len(passage) - len(passage.lstrip()))
            passages.append(
                {"name": entry["name"], "start": start, "title": "", "text": passage, "page": page}
            )
    return passages
