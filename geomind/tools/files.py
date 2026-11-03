"""The files of a project: ``list_files`` and ``read_document``.

A project's files come from the optional ``Workspace.files`` and ``Workspace.file``. A workspace
without them gets ``files_unavailable``, so a backend that has not added them keeps working.
"""

import csv
import difflib
import io
from pathlib import Path

from geomind.errors import ToolError
from geomind.stores.documents import document_text
from geomind.tools.base import tool
from geomind.tools.stored import reference_of
from geomind.utils.strings import join_names

PAGE_CHARACTERS = 20_000
"""The most text one ``read_document`` call returns; a longer file is read by pages."""
FIRST_ROWS = 5
TABLE_SUFFIXES = {".csv": ",", ".tsv": "\t"}


def file_name_schema():
    """Return the JSON Schema of an argument naming a project file; the pattern is not enforced."""
    return {
        "type": "string",
        "pattern": "^[^/\\\\].*$",
        "examples": ["demand.csv"],
        "description": "A file of the project such as 'demand.csv'; list_files lists them.",
    }


def file_names_schema():
    """Return the JSON Schema of an argument listing project files, or ``null``."""
    names = {"type": "array", "items": file_name_schema()}
    description = "Files of the project, such as ['demand.csv'], that the case names by this name."
    return {"anyOf": [names, {"type": "null"}], "default": None, "description": description}


def has_files(workspace):
    """Tell whether a workspace has the optional file methods."""
    return callable(getattr(workspace, "files", None)) and callable(
        getattr(workspace, "file", None)
    )


def project_file_names(context):
    """Return the names of the project's files; none without a project or the methods."""
    workspace = context.session.workspace
    if context.project is None or not has_files(workspace):
        return []
    return [item["name"] for item in workspace.files(context.project) or []]


def files_workspace(context, tool_name):
    """Return the run's workspace, or raise what the model should know about its files."""
    workspace = context.session.workspace
    if workspace is None or context.project is None:
        raise ToolError(
            f"{tool_name}: this run has no project; expected a workspace and one",
            code="not_allowed",
        )
    if not has_files(workspace):
        raise ToolError(
            f"{tool_name}: this workspace cannot list files; ask the user for the values",
            code="files_unavailable",
        )
    return workspace


def project_file(context, tool_name, name):
    """Return the bytes of a project file; an unknown name lists the project's files."""
    workspace = files_workspace(context, tool_name)
    content = workspace.file(context.project, name)
    if content is not None:
        return content
    names = project_file_names(context)
    raise ToolError(
        f"{tool_name}: file = {name!r}; expected one of {join_names(names)}",
        code="unknown_name",
        path="name",
        suggestions=difflib.get_close_matches(name, names),
    )


def table_of(name, text):
    """Return ``{columns, rows, first_rows}`` of a CSV or TSV, or ``None`` for another file."""
    delimiter = TABLE_SUFFIXES.get(Path(name).suffix.lower())
    if delimiter is None:
        return None
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row]
    if not rows:
        return None
    return {"columns": rows[0], "rows": len(rows) - 1, "first_rows": rows[1:][:FIRST_ROWS]}


@tool(effect="read")
def list_files(context):
    """List the files of the project: ``files``, each with ``name``, ``size`` and ``media_type``.

    Read one with ``read_document``, and give a data file to the case with ``set_case`` ``files``.
    """
    workspace = files_workspace(context, "list_files")
    return {"files": sorted(workspace.files(context.project), key=lambda item: item["name"])}


PAGE_NOTE = "already read in this run: read_stored a reference, or pass force=true"
WHOLE_NOTE = "the whole document was already read in this run: read_stored the references"
IN_CONVERSATION = "already read in this run: its text is in the conversation above"


def reads_of(context):
    """Return the reads of the run tree, ``{name: [read]}``: a nested run shares its root's."""
    session = getattr(context.session, "root_session", context.session)
    return getattr(session, "documents_read", None)


def read_before(context, name, start, end):
    """Return the earlier reads of ``name`` in this run covering ``start`` to ``end``, or ``None``.

    Each is ``{start, end, reference}``: ``reference`` is where the earlier result was stored, for
    ``read_stored``, or ``None`` when it was short enough to stay in the conversation. A read
    of another run of the tree counts only when its result was stored, as this run's
    conversation does not hold it.
    """
    run = context.session.state.run_id
    reads = [
        read
        for read in (reads_of(context) or {}).get(name, [])
        if read.get("run") == run or stored_reference(context, read)
    ]
    covered, position = [], start
    for read in sorted(reads, key=lambda item: item["start"]):
        if read["start"] <= position < read["end"]:
            covered.append(read)
            position = read["end"]
    if not covered or position < end:
        return None
    return [{**read, "reference": stored_reference(context, read)} for read in covered]


def stored_reference(context, read):
    """Return the reference of an earlier read if its result was stored, else ``None``."""
    reference = read["reference"]
    return reference if reference and context.session.load_artifact(reference) else None


def remember_read(context, name, start, end):
    """Keep that this run read ``name`` from ``start`` to ``end``, with where its result goes."""
    reads = reads_of(context)
    if reads is None:
        return
    reference = reference_of(context.call_id) if context.call_id else None
    read = {"start": start, "end": end, "reference": reference, "run": context.session.state.run_id}
    reads.setdefault(name, []).append(read)


def document_bytes(context, name):
    """Return the bytes of a project file, or of ``knowledge/<name>`` of the knowledge base."""
    from geomind.tools.knowledge import PREFIX, knowledge_file

    if name.startswith(PREFIX):
        return knowledge_file(context, "read_document", name)
    return project_file(context, "read_document", name)


@tool(effect="read", late_schemas={"name": file_name_schema}, keeps_result=True)
def read_document(
    context, name: str, start: int = 0, length: int | None = None, force: bool = False
):
    """Read a project file, or a document of the knowledge base as ``knowledge/<name>``, as text.

    CSV, TSV, JSON, Markdown and text files read as they are, and a PDF as its extracted text with
    a ``[page n]`` marker before each page; another file is a ``not_text`` error. ``start`` is the
    first character and ``length`` the number of characters, at most 20,000. Returns ``name``,
    ``start``, ``total``, ``text`` and ``next``, where the following page starts (``null`` at the
    end). The first page of a CSV or TSV also has ``table``: ``columns``, the number of ``rows``
    and the ``first_rows``. A page this run already read comes back as ``already_read`` with a
    ``note`` instead of its text; ``force`` reads it again, until the whole document was read:
    then every page is ``already_read``, with the references of the stored results. Nested runs
    share what the run tree read.
    """
    if start < 0:
        raise ToolError(f"read_document: start = {start}; expected 0 or more", path="start")
    text = document_text(name, document_bytes(context, name))
    size = min(length or PAGE_CHARACTERS, PAGE_CHARACTERS)
    end = min(start + size, len(text))
    whole = read_before(context, name, 0, len(text))
    earlier = whole or (None if force else read_before(context, name, start, end))
    if earlier is not None:
        note = WHOLE_NOTE if whole else PAGE_NOTE
        if all(read["reference"] is None for read in earlier):
            note = IN_CONVERSATION
        return {
            "name": name,
            "start": start,
            "total": len(text),
            "already_read": earlier,
            "note": note,
        }
    remember_read(context, name, start, end)
    page = {"name": name, "start": start, "total": len(text), "text": text[start:end]}
    page["next"] = end if end < len(text) else None
    table = table_of(name, text) if start == 0 else None
    return page if table is None else {**page, "table": table}
