"""Tools and the decorator."""

import pydantic
import pytest

from geomind.errors import DeclarationError, ToolError, UnknownNameError
from geomind.tools import Tool, tool


@tool(effect="compute")
def add(left: int, right: int = 1):
    """Add two numbers.

    Second paragraph, with its
    two lines.

    NOTE: for people, not for the model.
    """
    return left + right


def test_decorator_builds_the_schema_from_the_signature():
    """Name, description and schema come from the function."""
    schema = add.schema()
    assert schema["name"] == "add"
    assert schema["description"] == "Add two numbers.\n\nSecond paragraph, with its two lines."
    assert schema["input_schema"]["required"] == ["left"]
    assert schema["input_schema"]["properties"]["left"]["type"] == "integer"


def test_a_late_schema_is_read_when_the_tool_is_offered():
    """The stored schema stays plain, and the definitions move to the top of the offered one."""
    late = {"type": "object", "$defs": {"Port": {"type": "string"}}}

    @tool(effect="write", late_schemas={"value": lambda: late})
    def store(value: dict):
        """Store."""

    offered = store.schema()["input_schema"]
    assert offered["properties"]["value"] == {"type": "object"}
    assert offered["$defs"] == late["$defs"]
    assert "$defs" not in store.input_schema


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


def test_the_offered_schema_has_no_title_annotations_but_keeps_a_property_named_title():
    """Titles only repeat names; a field called ``title`` is still offered."""

    @tool(effect="read")
    def titled(title: str, count: int):
        """Take two fields."""

    offered = titled.schema()["input_schema"]
    assert "title" in offered["properties"] and "title" not in offered
    assert all("title" not in value for value in offered["properties"].values())


def test_a_renamed_tool_answers_to_its_old_name_for_old_logs():
    """``read_document`` of an older log finds ``read_rag``; old names stay replayable."""
    from geomind.tools import read_rag
    from geomind.tools.base import with_old_names

    tools = with_old_names({"read_rag": read_rag})
    assert tools["read_document"] is read_rag and "search_documents" not in tools


def test_the_rag_tools_of_dev41_logs_find_their_new_names():
    """``rag_read``, ``rag_search`` and ``search_knowledge`` of older logs still replay."""
    from geomind.tools import read_rag, search_rag
    from geomind.tools.base import with_old_names

    tools = with_old_names({"read_rag": read_rag, "search_rag": search_rag})
    assert tools["rag_read"] is read_rag and tools["rag_search"] is search_rag
    assert tools["search_knowledge"] is search_rag


@tool(effect="write")
def patch(changes: dict | None = None, files: list[str] | None = None, source: str | None = None):
    """Patch."""


def test_an_object_sent_as_json_text_is_read_as_the_object():
    """An object or array argument sent as its JSON text is used parsed (#67)."""
    changes = '{"format": 1, "site": {"name": "a"}}'
    arguments = patch.validate({"changes": changes, "files": '["x"]'})
    assert arguments["changes"] == {"format": 1, "site": {"name": "a"}}
    assert arguments["files"] == ["x"]


@pytest.mark.parametrize("value", ["not json", '"a string"', "[1, 2]", "3"])
def test_an_object_sent_as_other_text_is_still_refused(value):
    """Text that is no JSON object, for an object parameter, is refused as before."""
    with pytest.raises(pydantic.ValidationError, match="valid dictionary"):
        patch.validate({"changes": value})


def test_a_string_parameter_keeps_its_json_looking_string():
    """A string parameter is never parsed, even when its value is JSON text."""
    assert patch.validate({"source": '{"a": 1}'})["source"] == '{"a": 1}'


def test_a_model_parameter_sent_as_json_text_is_read_through_its_definition():
    """A parameter typed by a model (a ``$ref``) takes its JSON text too, as a hand-made tool."""

    class Point(pydantic.BaseModel):
        x: int

    @tool(effect="compute")
    def move(point: Point):
        """Move."""

    assert move.validate({"point": '{"x": 2}'})["point"] == Point(x=2)
    schema = {"properties": {"a": {"type": "object"}, "b": {}}, "required": ["a"]}
    hand_made = Tool("t", "d", schema, print, effect="read")
    arguments = hand_made.validate({"a": '{"k": 1}', "b": '{"k": 1}'})
    assert arguments == {"a": {"k": 1}, "b": '{"k": 1}'}
