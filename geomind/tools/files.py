"""The files of a project: ``list_files`` and ``read_rag``.

A project's files come from the optional ``Workspace.files`` and ``Workspace.file``. A workspace
without them gets ``files_unavailable``, so a backend that has not added them keeps working.
"""

import csv
import difflib
import io
from pathlib import Path

from geomind.errors import ToolError
from geomind.stores.documents import document_text
from geomind.tools import sections
from geomind.tools.base import tool
from geomind.tools.stored import reference_of
from geomind.utils.strings import join_names

PAGE_CHARACTERS = 20_000
"""The most text one ``read_rag`` call returns; a longer file is read by pages."""
LARGE_TABLE_CHARACTERS = PAGE_CHARACTERS
"""The longest CSV or TSV ``read_rag`` returns as text; a longer one gives its outline only.

A model read a 79,000-character cost catalogue whole and by pages, and every later step carried
it (B6): a larger table is read by ``rows`` and ``columns``, after ``search_rag`` found the rows.
"""
LARGE_TABLE_NOTE = (
    "this table is {total} characters, more than the {limit} read_rag returns as text, so only its "
    "outline is here (table: columns, rows, first rows). Find the rows you need with "
    "search_rag(query), then read only them: rows={{column: [start of the value, ...]}}, such as "
    "the keys you miss in a column of paths, and columns=[...] with the fields you need"
)
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


STEP_UNITS = ("d", "h", "min", "s")


def _step(seconds):
    """Return a step as a case writes it, ``{value, unit}`` in the largest whole unit."""
    import gemini as gm

    for unit in STEP_UNITS:
        value = gm.units.convert(seconds, "s", unit)
        if float(value).is_integer():
            return {"value": int(value), "unit": unit}
    return {"value": seconds, "unit": "s"}


def _time_text(time, like):
    """Return ``time`` written as ``like`` is: a date alone, or a time with ``Z`` for UTC."""
    if len(like) == len("2000-01-01"):
        return time.date().isoformat()
    text = time.isoformat()
    return text.replace("+00:00", "Z") if like.endswith("Z") else text


def span_of(rows):
    """Return ``{start, end, step}`` of a first column of evenly spaced times, else ``None``.

    ``end`` is exclusive, one step after the last row, as a case's ``time.end`` is, so the case's
    span is copied from the file and never worked out by hand.
    """
    from datetime import datetime

    try:
        times = [datetime.fromisoformat(row[0]) for row in rows]
    except ValueError:
        return None
    steps = {later - earlier for earlier, later in zip(times, times[1:], strict=False)}
    if len(steps) != 1:
        return None
    seconds = int(steps.pop().total_seconds())
    if seconds <= 0:
        return None
    end = times[-1] + (times[1] - times[0])
    return {"start": rows[0][0], "end": _time_text(end, rows[-1][0]), "step": _step(seconds)}


def only_columns(name, text, columns):
    """Return a table's text with only ``columns``, in that order; another file is an error."""
    delimiter = table_delimiter(name, "columns", columns)
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row]
    header = rows[0] if rows else []
    unknown = [column for column in columns if column not in header]
    if unknown or not columns:
        raise ToolError(
            f"read_rag: columns = {columns!r}; expected some of {join_names(header)}",
            code="unknown_name",
            path="columns",
            suggestions=[
                match for item in unknown for match in difflib.get_close_matches(item, header)
            ],
        )
    picked = [header.index(column) for column in columns]
    out = io.StringIO()
    writer = csv.writer(out, delimiter=delimiter, lineterminator="\n")
    for row in rows:
        writer.writerow([row[index] if index < len(row) else "" for index in picked])
    return out.getvalue()


def table_delimiter(name, argument, value):
    """Return the delimiter of a CSV or TSV; ``argument`` given for another file is an error."""
    delimiter = TABLE_SUFFIXES.get(Path(name).suffix.lower())
    if delimiter is None:
        raise ToolError(
            f"read_rag: {argument} = {value!r}; expected none for {name!r}, which is no CSV or TSV",
            path=argument,
        )
    return delimiter


def only_rows(name, text, rows):
    """Return a table's text with its header and the rows ``rows`` asks for.

    ``rows`` is ``{column: [text, ...]}``: a row is kept when, in every named column, its value
    starts with one of the texts, such as the paths of the keys a case lacks.
    """
    delimiter = table_delimiter(name, "rows", rows)
    table = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row]
    header = table[0] if table else []
    unknown = [column for column in rows if column not in header]
    if unknown or not rows:
        raise ToolError(
            f"read_rag: rows = {rows!r}; expected columns among {join_names(header)}",
            code="unknown_name",
            path="rows",
            suggestions=[
                match for item in unknown for match in difflib.get_close_matches(item, header)
            ],
        )
    starts = {
        header.index(column): (texts,) if isinstance(texts, str) else tuple(texts)
        for column, texts in rows.items()
    }
    kept = [
        row
        for row in table[1:]
        if all(index < len(row) and row[index].startswith(texts) for index, texts in starts.items())
    ]
    out = io.StringIO()
    csv.writer(out, delimiter=delimiter, lineterminator="\n").writerows([header, *kept])
    return out.getvalue()


def narrowed(name, text, rows, columns):
    """Return a document's text after ``rows`` and ``columns``, and the key its reads go by."""
    key = name
    if rows is not None:
        text = only_rows(name, text, rows)
        key = f"{key}#rows={sorted(rows.items())}"
    if columns is not None:
        text = only_columns(name, text, columns)
        key = f"{key}#{','.join(columns)}"
    return text, key


def large_table(name, text):
    """Return what a table over ``LARGE_TABLE_CHARACTERS`` gives: its size, outline and note."""
    note = LARGE_TABLE_NOTE.format(total=len(text), limit=LARGE_TABLE_CHARACTERS)
    return {"total": len(text), "table": table_of(name, text), "note": note}


def table_of(name, text):
    """Return ``{columns, rows, first_rows, last_row, span}`` of a CSV or TSV, else ``None``.

    ``span`` is the case's time the rows cover, from :func:`span_of`, or ``None``.
    """
    delimiter = TABLE_SUFFIXES.get(Path(name).suffix.lower())
    if delimiter is None:
        return None
    rows = [row for row in csv.reader(io.StringIO(text), delimiter=delimiter) if row]
    if not rows:
        return None
    return {
        "columns": rows[0],
        "rows": len(rows) - 1,
        "first_rows": rows[1:][:FIRST_ROWS],
        "last_row": rows[-1] if len(rows) > 1 else None,
        "span": span_of(rows[1:]),
    }


@tool(effect="read")
def list_files(context):
    """List the files of the project: ``files``, each with ``name``, ``size`` and ``media_type``.

    Skill `finding-sources`.
    """
    workspace = files_workspace(context, "list_files")
    return {"files": sorted(workspace.files(context.project), key=lambda item: item["name"])}


PAGE_NOTE = "already read in this run: read_stored a reference, or pass force=true"
WHOLE_NOTE = "the whole document was already read in this run: read_stored the references"
IN_CONVERSATION = "already read at step {step}; its text is in your context; {next}"
"""The note of a page this run read with no compaction since, ``force`` or not (#120, #122).

DeepSeek, told the text was in the conversation, read the same pages 48 times in one run and
never called ``set_case``: the note names the step of the read and, for an agent that sets the
case, the next call.
"""

AFTER_COMPACTION = (
    "already read in this run, before a compaction summarized it: read_stored a reference"
)


def next_call(context):
    """Return what the note tells the agent to do next: ``set_case`` where it has that tool."""
    agent = getattr(context.session, "agent", None)
    tools = agent.tools() if agent is not None else {}
    return "call set_case next" if "set_case" in tools else "work from it"


def in_conversation(context, step):
    """Return the note of a page read at ``step`` that is still in the conversation."""
    return IN_CONVERSATION.format(step=step, next=next_call(context))


def reads_of(context):
    """Return the reads of the run tree, ``{name: [read]}``: a nested run shares its root's."""
    session = getattr(context.session, "root_session", context.session)
    return getattr(session, "documents_read", None)


def read_before(context, name, start, end):
    """Return the earlier reads of ``name`` in this run covering ``start`` to ``end``, or ``None``.

    Each is ``{start, end, reference}``: ``reference`` is where the earlier result was stored, for
    ``read_stored`` after a compaction, or ``None``. Only this run's reads count: a page another
    run of the tree read is not in this run's conversation, so this run reads it itself, once,
    instead of a note and a ``read_stored`` call.
    """
    run = context.session.state.run_id
    reads = [read for read in (reads_of(context) or {}).get(name, []) if read.get("run") == run]
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
    state = context.session.state
    read = {"start": start, "end": end, "reference": reference, "run": state.run_id}
    read["step"] = getattr(state, "step", None)
    reads.setdefault(name, []).append({**read, "compacted": compacted_turns(context)})


def compacted_turns(context):
    """Return how many turns compactions have summarized so far, 0 without one."""
    problem = getattr(context, "problem", None)
    compaction = getattr(problem, "compaction", None)
    return compaction.turns if compaction else 0


def compacted_since(context, earlier):
    """Tell whether a compaction summarized turns since any of the ``earlier`` reads."""
    return any(read["compacted"] < compacted_turns(context) for read in earlier)


def document_bytes(context, name):
    """Return the bytes of a project file, or of ``knowledge/<name>`` of the knowledge base."""
    from geomind.tools.knowledge import PREFIX, knowledge_file

    if name.startswith(PREFIX):
        return knowledge_file(context, "read_rag", name)
    return project_file(context, "read_rag", name)


def section_text(name, text, key, section):
    """Return ``(section text, read key, heading)`` of the section ``section`` names, or refuse."""
    found = sections.section_span(text, section)
    if found is None:
        listed = ", ".join(sections.label(item) for item in sections.headings(text))
        raise ToolError(
            f"read_rag: section = {section!r} is no heading of {name}; expected a number or a "
            f"title of its outline (read_rag(name, outline=true)): {listed[:1500] or 'it has none'}",
            code="unknown_name",
            path="section",
        )
    return text[found["start"] : found["end"]], f"{key}#{found['number']}", found


@tool(effect="read", late_schemas={"name": file_name_schema}, keeps_result="run")
def read_rag(
    context,
    name: str,
    start: int = 0,
    length: int | None = None,
    force: bool = False,
    columns: list[str] | None = None,
    rows: dict[str, list[str] | str] | None = None,
    outline: bool = False,
    section: str | None = None,
):
    """Read a project file, or a document of the knowledge base as ``knowledge/<name>``, as text.

    Skill `finding-sources`.
    """
    if start < 0:
        raise ToolError(f"read_rag: start = {start}; expected 0 or more", path="start")
    text, key = narrowed(name, document_text(name, document_bytes(context, name)), rows, columns)
    if outline:
        return {"name": name, "total": len(text), "outline": sections.outline(text)}
    if section is not None:
        text, key, found = section_text(name, text, key, section)
        name_shown = {"section": {k: found[k] for k in ("number", "title", "start", "size")}}
    else:
        name_shown = {}
    shown = {"name": name, **name_shown, **({"columns": columns} if columns is not None else {})}
    shown = {**shown, **({"rows": rows} if rows is not None else {})}
    if len(text) > LARGE_TABLE_CHARACTERS and Path(name).suffix.lower() in TABLE_SUFFIXES:
        return {**shown, "start": start, **large_table(name, text)}
    size = min(length or PAGE_CHARACTERS, PAGE_CHARACTERS)
    end = min(start + size, len(text))
    whole = read_before(context, key, 0, len(text))
    earlier = whole or read_before(context, key, start, end)
    if earlier is not None and force and not whole and compacted_since(context, earlier):
        earlier = None
    if earlier is not None:
        note = WHOLE_NOTE if whole else PAGE_NOTE
        this_run = context.session.state.run_id
        hidden = {"compacted"}
        if all(read["reference"] is None or read["run"] == this_run for read in earlier):
            compacted = compacted_since(context, earlier)
            step = max((read.get("step") or 0 for read in earlier), default=0)
            note = AFTER_COMPACTION if compacted else in_conversation(context, step)
            hidden |= set() if compacted else {"reference"}
        earlier = [{k: v for k, v in read.items() if k not in hidden} for read in earlier]
        return {**shown, "start": start, "total": len(text), "already_read": earlier, "note": note}
    remember_read(context, key, start, end)
    page = {**shown, "start": start, "total": len(text), "text": text[start:end]}
    page["next"] = end if end < len(text) else None
    table = table_of(name, text) if start == 0 else None
    return page if table is None else {**page, "table": table}
