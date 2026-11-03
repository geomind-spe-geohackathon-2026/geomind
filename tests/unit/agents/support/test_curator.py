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
    assert "A user fact's source is `user`" in text


def test_its_prompt_says_every_field_of_an_entry_and_the_roles():
    """#96: a lesson named the project's brief; the fields and the roles come with their rules."""
    from geomind.agents.support.curator import agent_roles

    text = " ".join(Curator().prompt.render().split())
    assert "no name of the project, its files or its brief" in text
    assert all(f"`{role}`" in text for role in agent_roles())
    assert "Don't: `geoscientist`" in text


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_CURATOR_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_CURATOR_MODEL", raising=False)
    assert runtime.role_models()["curator"] is None


def test_every_agent_s_snake_name_is_a_role_a_lesson_may_name():
    """The tool's check (the role settings) and the prompt's list (the agents) agree."""
    from geomind.agents.support.curator import agent_roles
    from geomind.tools.memory import is_role

    assert all(is_role(role) for role in agent_roles()) and not is_role("designlead")


def test_with_the_memory_off_it_calls_no_memory_tool():
    """#99: nemotron called the memory tools it was not offered; the prompt says how to tell."""
    text = " ".join(Curator().prompt.content.split())
    assert "are not among the tools you are offered: then call no memory tool at all" in text
