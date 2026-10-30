"""The tool that reads a skill."""

from geomind.tools import read_skill


def test_read_skill_is_a_read():
    """Reading instructions needs no approval."""
    assert read_skill.effect == "read"


def test_read_skill_returns_the_text():
    """The tool passes the name on."""
    assert read_skill.function("gemini-units").startswith("Units gemini accepts")
