"""Tools and the decorator."""

import pydantic
import pytest

from swarmax.errors import DeclarationError, ToolError, UnknownNameError
from swarmax.tools import Tool, tool


@tool(effect="compute")
def add(left: int, right: int = 1):
    """Add two numbers.

    Second paragraph.
    """
    return left + right


def test_decorator_builds_the_schema_from_the_signature():
    """Name, description and schema come from the function."""
    schema = add.schema()
    assert (schema["name"], schema["description"]) == ("add", "Add two numbers.")
    assert schema["input_schema"]["required"] == ["left"]
    assert schema["input_schema"]["properties"]["left"]["type"] == "integer"


def test_validate_fills_defaults_and_converts():
    """Valid input becomes keyword arguments."""
    assert add.validate({"left": 2}) == {"left": 2, "right": 1}


@pytest.mark.parametrize("tool_input", [{}, {"left": "x"}, {"left": 1, "other": 2}])
def test_validate_rejects_a_wrong_input(tool_input):
    """Missing, wrong and unknown names raise."""
    with pytest.raises(pydantic.ValidationError):
        add.validate(tool_input)


def test_hand_made_tool_checks_names_only():
    """A tool from another source still rejects missing and unknown names."""
    schema = {"properties": {"a": {}}, "required": ["a"]}
    hand_made = Tool("t", "d", schema, print, effect="read")
    assert hand_made.validate({"a": 1}) == {"a": 1}
    with pytest.raises(ToolError, match="missing"):
        hand_made.validate({"b": 1})


def test_unknown_effect_suggests_a_name():
    """An effect is one of five."""
    with pytest.raises(UnknownNameError, match="did you mean 'read'"):
        Tool("t", "d", {}, print, effect="reed")


def test_function_needs_annotations_and_a_docstring():
    """The schema cannot be guessed."""

    def missing_annotation(value):
        """Say something."""

    def missing_docstring(value: int):
        pass

    with pytest.raises(DeclarationError, match="type annotation"):
        tool(effect="read")(missing_annotation)
    with pytest.raises(DeclarationError, match="docstring"):
        tool(effect="read")(missing_docstring)


def test_only_read_and_compute_are_pure():
    """Pure tools run together and again in a replay."""
    assert add.is_pure and Tool("t", "d", {}, print, effect="read").is_pure
    assert not Tool("t", "d", {}, print, effect="write").is_pure


def test_renamed_leaves_the_original_alone():
    """An agent's attribute name wins on its own copy."""
    assert add.renamed("sum").name == "sum" and add.name == "add"
