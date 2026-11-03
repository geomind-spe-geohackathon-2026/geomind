"""``search_knowledge`` and ``read_document`` of ``knowledge/<name>``."""

from geomind.stores import MemoryWorkspace
from geomind.stores.knowledge import MemoryKnowledge
from geomind.tools import read_document, search_knowledge
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

REPORT = b"Drilling report\n\nThe net drilling cost was high.\n\nPumps ran well."


def session_with(knowledge):
    """Return a session whose workspace holds ``knowledge``."""
    return StubSession(workspace=MemoryWorkspace(knowledge=knowledge))


async def test_a_search_returns_passages_with_their_citation():
    """Each passage names its document, title and page, best first."""
    session = session_with(MemoryKnowledge({"report.md": REPORT}))
    passages = (await call(search_knowledge, {"query": "drilling cost"}, session)).output[
        "passages"
    ]
    assert passages[0]["document"] == "report.md" and passages[0]["title"] == "Drilling report"
    assert {"id", "page", "text", "score"} <= set(passages[0])


async def test_no_knowledge_base_is_knowledge_unavailable():
    """A workspace without the methods, or without documents, says so; it is no crash."""
    for session in (StubSession(), session_with(MemoryKnowledge({}))):
        error = (await call(search_knowledge, {"query": "x"}, session)).output["error"]
        assert error["code"] == "knowledge_unavailable"


async def test_read_document_reads_a_document_of_the_knowledge_base():
    """``knowledge/<name>`` reads the knowledge base's document; another name lists them."""
    session = session_with(MemoryKnowledge({"report.md": REPORT}))
    page = (await call(read_document, {"name": "knowledge/report.md"}, session)).output
    assert page["text"].startswith("Drilling report")
    missing = (await call(read_document, {"name": "knowledge/none.md"}, session)).output
    assert "knowledge/report.md" in missing["error"]["message"]
