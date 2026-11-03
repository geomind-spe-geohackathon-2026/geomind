"""System prompts."""

import pytest

from geomind.errors import UnknownNameError
from geomind.prompts import Prompt


def test_role_loads_its_file():
    """The assistant role has a shipped file."""
    assert "assistant" in Prompt("assistant").render()


def test_inline_text():
    """Inline text is stripped and kept."""
    assert Prompt.text("  Be brief.\n").render() == "Be brief."


def test_unknown_role_suggests_a_name():
    """A typo gets a close match."""
    with pytest.raises(UnknownNameError, match="did you mean 'assistant'"):
        Prompt("asistant")


def test_the_shared_text_names_the_tool_it_is_given_with():
    """The texts added for the shared tools name each tool the shared set holds."""
    from geomind.prompts.prompt import MEMORY, SHARED_TOOLS, STORED_RESULTS

    assert all(f"`{name}" in STORED_RESULTS + MEMORY for name in SHARED_TOOLS)
