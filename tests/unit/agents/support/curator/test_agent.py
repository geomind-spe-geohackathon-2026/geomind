"""The curator: keeps the run's general lessons per role and the user's facts."""

from geomind import runtime
from geomind.agents import Curator
from tests.unit.agents.structure import check_complete

TOOLS = ["read_case", "read_stored", "search_memory", "read_memory", "write_lesson", "finish"]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(Curator, "support/curator", TOOLS)


def test_it_writes_lessons_never_designs_or_knowledge():
    """No ``write_memory``: designs are code's, after the reviewer passed them."""
    tools = set(Curator().tools())
    assert "write_lesson" in tools and "write_memory" not in tools


def test_its_prompt_keeps_method_never_numbers():
    """A lesson is method in words; the user's facts carry the source ``user``."""
    text = Curator().prompt.content
    assert "never keep a project's numbers as a rule" in text
    assert "`user_fact` with `source` `user`" in text


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_CURATOR_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_CURATOR_MODEL", raising=False)
    assert runtime.role_models()["curator"] is None
