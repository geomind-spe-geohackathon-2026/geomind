"""Tools and the decorator."""

import json

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


async def test_a_list_sent_as_its_json_text_is_read_as_the_list():
    """#87: nemotron sent ``changes`` of update_state as a JSON string; two refusals ended a run."""
    from geomind.tools import update_state

    changes = [{"op": "add", "path": "/goal", "value": "cost it"}]
    assert update_state.validate({"changes": json.dumps(changes)}) == {"changes": changes}


def test_a_string_that_is_no_container_stays_for_the_schema_to_judge():
    """Only JSON text of the type the schema asks for is read; other text is left as it came."""
    from geomind.tools.base import decoded_containers

    schema = {"properties": {"changes": {"type": "array"}, "note": {"type": "string"}}}
    assert decoded_containers({"changes": "{}", "note": "[1]"}, schema) == {
        "changes": "{}",
        "note": "[1]",
    }
