"""``search_rag`` over the knowledge base, and ``read_rag`` of ``knowledge/<name>``."""

import json
from pathlib import Path

from geomind.stores import MemoryWorkspace
from geomind.stores.knowledge import MemoryKnowledge
from geomind.tools import read_rag, search_rag
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

REPORT = b"Drilling report\n\nThe net drilling cost was high.\n\nPumps ran well."
BRIEF = b"Brief\n\nThe drilling depth may change."


def session_with(knowledge, files=None):
    """Return a session whose workspace holds ``knowledge`` and, if given, project files."""
    workspace = MemoryWorkspace(knowledge=knowledge, files={"p": files} if files else None)
    return StubSession(workspace=workspace)


async def test_a_search_of_the_knowledge_base_cites_each_passage():
    """A knowledge match has its scope, a name ``read_rag`` reads and its document's citation."""
    session = session_with(MemoryKnowledge({"report.md": REPORT}))
    matches = (await call(search_rag, {"query": "drilling cost"}, session)).output["matches"]
    assert matches[0]["scope"] == "knowledge" and matches[0]["name"] == "knowledge/report.md"
    citation = matches[0]["citation"]
    assert citation["document"] == "report.md" and citation["title"] == "Drilling report"
    assert "page" in citation


async def test_one_search_finds_the_project_and_the_knowledge_base_in_turn():
    """Each scope's best come first, in turn: their scores come from different rankings."""
    session = session_with(MemoryKnowledge({"report.md": REPORT}), {"brief.md": BRIEF})
    matches = (await call(search_rag, {"query": "drilling"}, session, "p")).output["matches"]
    assert [item["scope"] for item in matches[:2]] == ["project", "knowledge"]
    assert matches[0]["citation"] == {"file": "brief.md", "page": None}


async def test_without_a_project_or_a_knowledge_base_the_search_is_not_allowed():
    """A run with neither has nothing to search; it is no crash."""
    error = (await call(search_rag, {"query": "x"}, StubSession())).output["error"]
    assert error["code"] == "not_allowed"


async def test_an_empty_knowledge_base_is_knowledge_unavailable_to_read():
    """A workspace without the methods, or without documents, says so; it is no crash."""
    for session in (StubSession(), session_with(MemoryKnowledge({}))):
        error = (await call(read_rag, {"name": "knowledge/a.md"}, session)).output["error"]
        assert error["code"] == "knowledge_unavailable"


async def test_read_rag_reads_a_document_of_the_knowledge_base():
    """``knowledge/<name>`` reads the knowledge base's document; another name lists them."""
    session = session_with(MemoryKnowledge({"report.md": REPORT}))
    page = (await call(read_rag, {"name": "knowledge/report.md"}, session)).output
    assert page["text"].startswith("Drilling report")
    missing = (await call(read_rag, {"name": "knowledge/none.md"}, session)).output
    assert "knowledge/report.md" in missing["error"]["message"]


CATALOGUE = (Path(__file__).parents[3] / "data" / "knowledge" / "cost-sources.csv").read_bytes()
"""geomind's copy of the cost catalogue: about 79,000 characters, one row per cited value."""
CATALOGUE_ROWS = len(CATALOGUE.decode().strip().splitlines()) - 1
"""The catalogue's rows below its header, counted from the file, not pinned."""
WIDE = ["id", "path", "value_2015", "unit_2015", "status", "source", "year", "url"]
"""The columns the case lead read the catalogue with in run c8bf2381: still over a page."""


async def test_a_large_table_is_outlined_never_read_whole_or_by_pages():
    """B6: a table over ``LARGE_TABLE_CHARACTERS`` gives its outline and a note, never its text.

    The case lead read the whole catalogue, then its pages, and each step after carried them:
    about 21 steps at 55-80k input tokens.
    """
    from geomind.tools.files import LARGE_TABLE_CHARACTERS

    session = session_with(MemoryKnowledge({"cost-sources.csv": CATALOGUE}))
    name = "knowledge/cost-sources.csv"
    for arguments in ({}, {"columns": WIDE}, {"columns": WIDE, "start": 20000}):
        page = (await call(read_rag, {"name": name, **arguments}, session)).output
        assert "text" not in page and page["total"] > LARGE_TABLE_CHARACTERS
        assert page["table"]["rows"] == CATALOGUE_ROWS and "path" in page["table"]["columns"]
        assert "search_rag" in page["note"] and "rows" in page["note"]
        assert len(json.dumps(page)) < 6000
    assert session.documents_read == {}


async def test_rows_reads_only_the_rows_whose_column_starts_with_a_given_text():
    """B6: ``rows`` keeps the header and the rows of the keys asked for, so the table fits."""
    session = session_with(MemoryKnowledge({"cost-sources.csv": CATALOGUE}))
    asked = {
        "name": "knowledge/cost-sources.csv",
        "columns": ["id", "path", "value_2015", "unit_2015"],
        "rows": {"path": ["economics.capex.drilling", "economics.opex.fixed"]},
    }
    page = (await call(read_rag, asked, session)).output
    lines = page["text"].splitlines()
    assert lines[0] == "id,path,value_2015,unit_2015" and len(lines) > 2
    prefixes = tuple(asked["rows"]["path"])
    assert all(line.split(",")[1].startswith(prefixes) for line in lines[1:])
    assert page["rows"] == asked["rows"] and page["next"] is None


async def test_rows_names_a_column_of_the_table():
    """An unknown column in ``rows`` is ``unknown_name`` with its close match; a text refuses it."""
    session = session_with(MemoryKnowledge({"cost-sources.csv": CATALOGUE, "report.md": REPORT}))
    asked = {"name": "knowledge/cost-sources.csv", "rows": {"paths": ["economics"]}}
    error = (await call(read_rag, asked, session)).output["error"]
    assert error["code"] == "unknown_name" and error["suggestions"] == ["path"]
    asked = {"name": "knowledge/report.md", "rows": {"path": ["economics"]}}
    assert (await call(read_rag, asked, session)).output["error"]["path"] == "rows"
