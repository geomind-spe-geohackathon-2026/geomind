"""Skills, loaded on demand."""

import pytest

from geomind.context.skills import load_skill, skill_listing, skill_names
from geomind.errors import UnknownNameError


def test_the_first_skills_ship():
    """The design lead's general skill, the units and the results skills exist."""
    assert skill_names() == [
        "designing-a-plant",
        "gemini-units",
        "reading-results",
    ]


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
    assert len(lines) == 4
    assert lines[2].startswith("- gemini-units: Units gemini accepts")


def test_a_tool_s_first_result_carries_its_skill_once():
    """A skill reaches an agent without read_skill: the first result of its tool carries it."""
    from geomind.context.skills import first_call_skill, tool_skills
    from geomind.types.messages import Message

    assert tool_skills()["evaluate_module"] == "evaluating-a-module"
    text = first_call_skill("evaluate_module", [])
    assert text.startswith("[skill evaluating-a-module, sent with the first call of evaluate_module]")
    later = [Message(role="tool", content=text, tool_call_id="c1")]
    assert first_call_skill("evaluate_module", later) is None
    assert first_call_skill("describe_module", later) is None
    assert first_call_skill("finish", []) is None
