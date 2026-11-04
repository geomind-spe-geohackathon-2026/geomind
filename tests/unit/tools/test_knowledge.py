"""``search_rag`` over the knowledge base, and ``read_rag`` of ``knowledge/<name>``."""

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
