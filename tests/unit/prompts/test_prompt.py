"""System prompts."""

import pytest

from swarmax.errors import UnknownNameError
from swarmax.prompts import Prompt


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
