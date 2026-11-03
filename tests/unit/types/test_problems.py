"""The shape of a tool's error result."""

import pytest
from pydantic import ValidationError

from geomind.types import TOOL_ERROR_CODES, Problem, ToolErrorOutput


def test_a_problem_has_gemini_keys():
    """The same four keys as gemini's Problem."""
    problem = Problem(code="timeout", message="too slow").model_dump(mode="json")
    assert problem == {"path": None, "code": "timeout", "message": "too slow", "suggestions": []}


def test_the_output_nests_one_problem():
    """An error result is ``{"error": problem}``."""
    output = ToolErrorOutput(error=Problem(code="internal", message="m"))
    assert output.error.code == "internal"


def test_a_problem_has_no_other_keys():
    """There is no ``class`` key: ``code`` is the key for machines."""
    with pytest.raises(ValidationError):
        Problem(code="internal", message="m", **{"class": "ToolError"})


def test_the_codes_are_the_fixed_list():
    """The list of ``tools.md``."""
    expected = {
        "invalid_input",
        "unknown_name",
        "not_implemented",
        "not_allowed",
        "no_case",
        "case_incomplete",
        "timeout",
        "budget",
    }
    assert set(TOOL_ERROR_CODES) == expected | {"internal"}
