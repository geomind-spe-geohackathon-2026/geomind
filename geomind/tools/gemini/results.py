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

    Skill `reading-results`.
    """
    if path is None and field is not None:
        raise ToolError(f"read_result: field = {field!r}; expected a path too", path="path")
    _, _, results = load_run(context, reference, "read_result")
    first, last = parse_time(start, "start", "read_result"), parse_time(end, "end", "read_result")
    if field is None:
        summary = results.summary(path=path, start=first, end=last, units=READ_UNITS)
        if path is None:
            return summary
        return {**summary, "operation": operation(results, path, first, last)}
    read = results.get(path, field, start=first, end=last, units=READ_UNITS)
    return {**read, "summary": series_summary(read)}


ENERGY_UNITS = {**READ_UNITS, "energy": "MWh", "duration": "h"}
"""The units of the energy report a module summary carries: energy in MWh, time in hours."""


def series_summary(read):
    """Return the facts of one series a question asks for, so no code has to count them.

    ``max`` and ``min`` carry the time of their first step, ``active_steps`` and ``active_days``
    count the steps and the calendar days (UTC) with a value other than zero, ``steps`` all steps.
    (QA-125: peaks, their days and active days took dozens of run_python steps.)
    """
    pairs = [
        (time, number)
        for time, number in zip(read["time"], read["value"])
        if isinstance(number, (int, float)) and not isinstance(number, bool)
    ]
    unit = read["unit"]
    summary = {"steps": len(read["time"]), "unit": unit}
    if not pairs:
        return {**summary, "note": "no numeric value in this window"}
    high = max(pairs, key=lambda pair: pair[1])
    low = min(pairs, key=lambda pair: pair[1])
    active = [time for time, number in pairs if number != 0]
    return {
        **summary,
        "max": {"value": high[1], "unit": unit, "time": high[0]},
        "min": {"value": low[1], "unit": unit, "time": low[0]},
        "mean": {"value": sum(number for _, number in pairs) / len(pairs), "unit": unit},
        "active_steps": len(active),
        "active_days": len({time[:10] for time in active}),
        "first_active": active[0] if active else None,
        "last_active": active[-1] if active else None,
    }


def operation(results, path, start, end):
    """Return how long one module ran and the energy of each of its energy outputs.

    ``operating_steps`` and ``operating_days`` count the steps and calendar days (UTC) with
    gemini's ``operating`` flag set (the module carried flow); ``energy`` is gemini's energy
    report per output (e.g. ``power_in``, ``fuel``) over the whole run, in MWh, without the
    module's empty entry: a module without an energy output (a heat exchanger) has none, which
    is not "unused" (QA-125, QA-123).
    """
    names = results.names().get(path, [])
    facts = {}
    if "operating" in names:
        read = results.get(path, "operating", start=start, end=end)
        steps = [time for time, flag in zip(read["time"], read["value"]) if flag]
        facts.update(
            steps=len(read["time"]),
            operating_steps=len(steps),
            operating_days=len({time[:10] for time in steps}),
        )
    report = results.energy_report(units=ENERGY_UNITS).get(path, {})
    energy = {port: entry["energy"] for port, entry in report.items() if port}
    if energy:
        facts["energy_whole_run"] = energy
    return facts


@tool(effect="read", keeps_result=True)
def search_rag(context, query: str):
    """Search the project's documents and files and the knowledge base; return ``{matches, note}``.

    Skill `finding-sources`.
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
    note = [NO_MATCH] if not matches else []
    if words_of(query) in searched_before(context):
        note.insert(0, SEARCHED)
    return {**result, "note": " ".join(note)} if note else result


def words_of(query):
    """Return the set of lower-case words of a query: the same words in any order are the same."""
    return frozenset(word.lower() for word in WORD.findall(str(query)))


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
            **hit_section(context, f"{PREFIX}{item['document']}", item["text"]),
        }
        for item in list(workspace.knowledge_search(query))[:SHOWN_MATCHES]
    ]


def hit_section(context, name, passage):
    """Return ``{"section": heading path}`` of a knowledge hit, or ``{}`` when it has none.

    The agent then reads the whole section with ``read_rag(name, section=...)``.
    """
    from geomind.tools.files import document_bytes, document_text
    from geomind.tools.sections import heading_path

    try:
        text = document_text(name, document_bytes(context, name))
    except Exception:
        return {}
    position = text.find(passage[:200].strip())
    path = heading_path(text, position) if position >= 0 else None
    return {"section": path} if path else {}


def page_at(text, position):
    """Return the number of the ``[page n]`` marker at or before ``position``, else ``None``."""
    markers = PAGE_MARKER.findall(text[: position + len("[page 0000]")])
    return int(markers[-1]) if markers else None


def searched_before(context):
    """Return the word sets of this run's ``search_rag`` calls before this call, in call order.

    They are read from the run's conversation, so a resumed run and a replay give the same note
    as the live run, also for two calls of one step that run together (#131): the first listed is
    the first searched, whichever finished first. A call outside a run's conversation has none.
    """
    found = set()
    for message in context.messages:
        for call in message.tool_calls if message.role == "assistant" else ():
            if call.id == context.call_id:
                return found
            if call.name == "search_rag":
                found.add(words_of(call.input.get("query", "")))
    return set()


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
