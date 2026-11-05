"""The sub-agents' Knowledge tools read only names inside ``knowledge/``."""

from geomind.errors import ToolError
from geomind.tools import knowledge_only


def test_a_bare_name_is_read_as_a_knowledge_document(monkeypatch):
    """QA-169: ``handbook-design.md`` reads ``knowledge/handbook-design.md``."""
    seen = []

    def read(context, name, **options):
        seen.append(name)
        return {"name": name}

    monkeypatch.setattr(knowledge_only.read_rag, "function", read)
    for name in ("handbook-design.md", "/handbook-design.md", "knowledge/handbook-design.md"):
        knowledge_only.read_knowledge.function(None, name)
    assert seen == ["knowledge/handbook-design.md"] * 3


def test_a_run_without_a_knowledge_base_is_not_allowed(monkeypatch):
    """No Knowledge base: the search says so, never an empty answer."""
    monkeypatch.setattr(knowledge_only, "knowledge_matches", lambda context, query: None)
    try:
        knowledge_only.search_knowledge.function(None, "flow")
    except ToolError as error:
        assert error.code == "not_allowed"
    else:
        raise AssertionError("search_knowledge answered without a Knowledge base")
