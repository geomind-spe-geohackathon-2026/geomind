"""System prompts."""

import pytest

from geomind.errors import UnknownNameError
from geomind.prompts import Prompt


def test_role_loads_its_file():
    """A role loads the ``prompt.md`` beside its agent, by ``<team>/<name>``."""
    assert "design lead" in Prompt("design/lead").render().lower()


def test_every_shipped_agent_has_its_prompt_beside_it():
    """Each role file sits in ``geomind/agents/<team>/<name>/`` beside its ``agent.py``."""
    from geomind.prompts.prompt import role_files

    files = role_files()
    assert files
    assert all((path.parent / "agent.py").exists() for path in files.values())


def test_inline_text():
    """Inline text is stripped and kept."""
    assert Prompt.text("  Be brief.\n").render() == "Be brief."


def test_unknown_role_suggests_a_name():
    """A typo gets a close match."""
    with pytest.raises(UnknownNameError, match="did you mean 'design/lead'"):
        Prompt("design/led")


def test_the_shared_text_names_the_tool_it_is_given_with():
    """The texts added for the shared tools name each tool the shared set holds."""
    from geomind.prompts.prompt import KNOWLEDGE, MEMORY, SHARED_TOOLS, STORED_RESULTS

    assert all(f"`{name}" in STORED_RESULTS + MEMORY + KNOWLEDGE for name in SHARED_TOOLS)
