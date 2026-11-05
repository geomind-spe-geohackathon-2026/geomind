"""Skills, loaded on demand."""

import pytest

from geomind.context.skills import load_skill, skill_listing, skill_names
from geomind.errors import UnknownNameError


def test_the_first_skills_ship():
    """The general skills and one skill per group of tools exist."""
    names = skill_names()
    for name in ("designing-a-plant", "gemini-units", "reading-results", "setting-the-case"):
        assert name in names
    assert names == sorted(names)


def test_a_skill_loads_by_name():
    """The file is returned whole."""
    assert "read_result" in load_skill("reading-results")


def test_an_unknown_skill_names_the_close_match():
    """A typo gets a suggestion."""
    with pytest.raises(UnknownNameError, match="did you mean 'gemini-units'"):
        load_skill("gemini-unit")


def test_a_name_cannot_leave_the_folder():
    """A path is an unknown name, not a file read."""
    with pytest.raises(UnknownNameError):
        load_skill("../general/assistant")


def test_the_listing_has_one_line_per_skill():
    """The system prompt holds names and one line each, not the text."""
    lines = skill_listing().splitlines()
    assert len(lines) == 1 + len(skill_names())
    assert any(line.startswith("- gemini-units: Units gemini accepts") for line in lines)


def test_a_tool_s_first_result_carries_its_skill_once():
    """A skill reaches an agent without read_skill: the first result of its tool carries it."""
    from geomind.context.skills import first_call_skill, tool_skills
    from geomind.types.messages import Message

    assert tool_skills()["evaluate_module"] == "evaluating-a-module"
    text = first_call_skill("evaluate_module", [])
    assert text.startswith(
        "[skill evaluating-a-module, sent with the first call of evaluate_module]"
    )
    later = [Message(role="tool", content=text, tool_call_id="c1")]
    assert first_call_skill("evaluate_module", later) is None
    assert first_call_skill("describe_module", later) is None
    assert first_call_skill("no_such_tool", []) is None


def test_every_tool_is_explained_by_exactly_one_skill():
    """User rule (2026-11-05): how to use a tool lives in one skill; its description names it."""
    from geomind import tools
    from geomind.context.skills import _skills
    from geomind.tools import mcp
    from geomind.tools.base import Tool

    found = {}
    for module in (tools, tools.gemini, mcp):
        for name in dir(module):
            item = getattr(module, name)
            if isinstance(item, Tool):
                found[item.name] = item
    claims = {}
    for skill, (fields, _) in _skills().items():
        for name in (part.strip() for part in fields["tools"].split(",")):
            if name.isidentifier():
                claims.setdefault(name, []).append(skill)
    assert sorted(set(found) - set(claims)) == []
    assert {name: skills for name, skills in claims.items() if len(skills) > 1} == {}
    for name, item in found.items():
        assert f"`{claims[name][0]}`" in item.description, name


def test_a_first_result_carries_the_skill_s_opening_and_its_own_section_only():
    """QA-273: the whole skill stayed in the history; now each tool's section comes once."""
    from geomind.context.skills import _skills, first_call_skill, tool_section
    from geomind.types.messages import Message

    first = first_call_skill("read_rag", [])
    assert tool_section("read_rag") in first and tool_section("search_rag") not in first
    assert "read_skill('finding-sources')" in first
    assert len(first) < len(_skills()["finding-sources"][1])
    later = [Message(role="tool", content=first, tool_call_id="c1")]
    second = first_call_skill("search_rag", later)
    assert second.startswith("[skill finding-sources, section of search_rag]")
    assert tool_section("search_rag") in second
    done = [*later, Message(role="tool", content=second, tool_call_id="c2")]
    assert first_call_skill("search_rag", done) is None
    assert first_call_skill("read_rag", done) is None
