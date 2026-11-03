"""The tools over a project's results and documents."""

from geomind.errors import ToolError
from geomind.stores.workspace import WORD, search
from geomind.tools.base import tool
from geomind.tools.files import document_text
from geomind.tools.gemini.references import reference_schema
from geomind.tools.gemini.runs import parse_time
from geomind.tools.gemini.stored import load_run

READ_UNITS = {
    "power": "MW",
    "temperature": "degC",
    "pressure": "bar",
    "volume_flow": "m3/h",
    "mass_flow": "kg/s",
}
"""The units in which the model reads a stored result: gemini's family keys for ``units=``."""


PASSAGE_CHARACTERS = 1500
"""The characters of one passage of a project file that ``search_documents`` returns."""
SHOWN_MATCHES = 8
"""The most matches ``search_documents`` returns, best first."""
NO_MATCH = (
    "no document or file of the project has these words, so it does not state this: choose a "
    "value and record it as an assumption with its reason, or ask_user; another wording finds "
    "nothing more"
)
SEARCHED = "already searched in this run with the same words:"


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


@tool(effect="read")
def search_documents(context, query: str):
    """Search the documents and the files of the project; return ``{matches, note}``, best first.

    A document match has ``id``, ``title``, ``text`` and ``score``. A file match is a passage of a
    file that reads as text, such as a PDF: ``name``, ``start`` (for ``read_document``), ``text``
    and ``score``; a file's name alone matches nothing. No match means the project does not state
    these words, and the ``note`` says what to do instead; the same words again are noted too.
    """
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError(
            "search_documents: this run has no project; expected a workspace and one",
            code="not_allowed",
        )
    found = list(workspace.documents(context.project, query))
    passages = search(file_passages(context), query)
    found += [{key: value for key, value in item.items() if key != "title"} for item in passages]
    matches = sorted(found, key=lambda item: item["score"], reverse=True)[:SHOWN_MATCHES]
    result = {"matches": matches}
    words = frozenset(word.lower() for word in WORD.findall(query))
    searched = searches_of(context)
    note = [NO_MATCH] if not matches else []
    if searched is not None and words in searched:
        note.insert(0, SEARCHED)
    if searched is not None:
        searched.add(words)
    return {**result, "note": " ".join(note)} if note else result


def searches_of(context):
    """Return the word sets the run tree searched, kept on its root session, or ``None``."""
    session = getattr(context.session, "root_session", context.session)
    return getattr(session, "searches", None)


def file_passages(context):
    """Return the passages of the project's files that read as text, ``PASSAGE_CHARACTERS`` each.

    A passage is ``{name, start, title, text}`` with an empty ``title``, so the file name is no
    match.
    """
    workspace = context.session.workspace
    files = workspace.files(context.project) if hasattr(workspace, "files") else []
    passages = []
    for entry in files:
        try:
            text = document_text(entry["name"], workspace.file(context.project, entry["name"]))
        except ToolError:
            continue
        for start in range(0, len(text), PASSAGE_CHARACTERS):
            passage = text[start : start + PASSAGE_CHARACTERS]
            passages.append({"name": entry["name"], "start": start, "title": "", "text": passage})
    return passages
