"""Tools and the decorator."""

import json
from pathlib import Path

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


def test_a_list_sent_as_json_text_is_the_list():
    """#112: nemotron sent ``changes`` as ``"[{...}]"``, twice; it means the list."""
    from geomind.tools.state import update_state

    changes = [{"op": "add", "path": "/goal", "value": "a plant"}]
    assert update_state.validate({"changes": json.dumps(changes)}) == {"changes": changes}
    stray = json.dumps(changes) + "}"
    assert update_state.validate({"changes": stray}) == {"changes": changes}


def test_text_that_is_no_json_of_the_type_still_fails():
    """A string that is not JSON of the type, or a field that wants text, is left as it is."""
    from pydantic import ValidationError

    from geomind.tools.state import update_state

    with pytest.raises(ValidationError):
        update_state.validate({"changes": '{"op": "add"}'})
    with pytest.raises(ValidationError):
        update_state.validate({"changes": "not json"})
    with pytest.raises(ValidationError):
        update_state.validate({"changes": '[{"op": "add"}] and more'})


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


async def test_a_list_sent_as_its_json_text_is_read_as_the_list():
    """#87: nemotron sent ``changes`` of update_state as a JSON string; two refusals ended a run."""
    from geomind.tools import update_state

    changes = [{"op": "add", "path": "/goal", "value": "cost it"}]
    assert update_state.validate({"changes": json.dumps(changes)}) == {"changes": changes}


def test_a_string_that_is_no_container_stays_for_the_schema_to_judge():
    """Only JSON text of the type the schema asks for is read; other text is left as it came."""
    from geomind.tools.base import parsed_inputs

    schema = {"properties": {"changes": {"type": "array"}, "note": {"type": "string"}}}
    assert parsed_inputs(schema, {"changes": "{}", "note": "[1]"}) == {
        "changes": "{}",
        "note": "[1]",
    }


def test_a_list_missing_only_its_closing_bracket_is_read():
    """#87: nemotron's JSON text of ``changes`` lacked its final ``]``, twice; the run stopped."""
    from geomind.tools.base import parsed_json

    assert parsed_json('[{"op": "add", "value": "a ] in text"}') == [
        {"op": "add", "value": "a ] in text"}
    ]
    assert parsed_json('{"a": [1}') is None


def test_a_null_sent_as_text_is_null_where_the_schema_takes_one():
    """A text ``"None"`` (nemotron's ``read_case``) is null; a required string stays as it came."""
    from geomind.tools.base import parsed_inputs

    schema = {
        "properties": {
            "section": {"anyOf": [{"type": "string"}, {"type": "null"}]},
            "name": {"type": "string"},
        }
    }
    assert parsed_inputs(schema, {"section": "None", "name": "None"}) == {
        "section": None,
        "name": "None",
    }


STRAY_BRACKETS = Path(__file__).parents[2] / "fixtures" / "live" / "a4_stray_brackets.json"
"""nemotron's JSON text of ``changes`` with a stray closing bracket mid-text, as recorded (#117)."""


def test_a_stray_closing_bracket_in_the_middle_is_deleted():
    """#117: ``}}}}, "requirements"`` and ``}}]}`` ended two nemotron runs; each is read now."""
    from geomind.tools.base import parsed_inputs

    recorded = json.loads(STRAY_BRACKETS.read_text())
    schema = {"properties": {"changes": {"anyOf": [{"type": "object"}, {"type": "null"}]}}}
    project = parsed_inputs(schema, {"changes": recorded["project_set_case_2"]})["changes"]
    assert project["requirements"]["doublet_count"]["max"] == 3
    assert project["demand"]["cooling"]["supply_temperature"] == {"value": 20, "unit": "°C"}
    chat = parsed_inputs(schema, {"changes": recorded["from_chat_set_case_1"]})["changes"]
    assert chat["demand"]["cooling"]["power"] == {"value": 5, "unit": "MW"}
    listed = {"properties": {"changes": {"type": "array"}}}
    state = parsed_inputs(listed, {"changes": recorded["from_files_update_state_1"]})["changes"]
    assert state[0]["value"]["citation"]["note"] == "dates 2027-01-01 to 2027-12-31, no offset"


def test_a_stray_bracket_before_the_next_key_and_the_limits_of_the_repair():
    """The bracket that closed the object early goes; a missing bracket is never made up."""
    from geomind.tools.base import parsed_json

    text = '{"opex": {"chemical": {"value": 2, "unit": "EUR/kg"}}}, "revenue": {"heat": 1}}'
    assert parsed_json(text) == {
        "opex": {"chemical": {"value": 2, "unit": "EUR/kg"}},
        "revenue": {"heat": 1},
    }
    assert parsed_json('{"a": "x}, y"}}, "b": 1}') == {"a": "x}, y", "b": 1}
    assert parsed_json('{"a": [1}') is None
    assert parsed_json('{"a": 1}, "b": 2}, "c": 3}, "d": 4}, "e": 5}') is None


EARLY_CLOSE = Path(__file__).parents[2] / "fixtures" / "live" / "h_update_state_early_close.json"
"""nemotron's ``update_state changes`` as JSON text in the end-to-end run, as recorded (#129)."""


def test_a_list_whose_object_closed_before_its_last_key_is_read():
    """#129: ``"reason": "x"}, "citation": null}]`` was refused "Input should be a valid list"."""
    from geomind.tools import update_state
    from geomind.tools.base import parsed_json

    recorded = json.loads(EARLY_CLOSE.read_text())["design_update_state_changes"]
    [change] = update_state.validate({"changes": recorded})["changes"]
    assert change["path"] == "/assumptions/-" and change["value"]["id"] == "A7"
    assert change["citation"] is None and change["reason"].startswith("No project plant")
    assert parsed_json('["a": 1]') is None


def test_a_list_of_model_refs_or_null_sent_as_json_text_is_the_list():
    """A list whose items are ``$ref`` definitions, in an ``anyOf`` with null, is read too."""
    from geomind.tools.base import parsed_inputs

    schema = {
        "properties": {
            "items": {
                "anyOf": [{"type": "array", "items": {"$ref": "#/$defs/Item"}}, {"type": "null"}]
            }
        },
        "$defs": {"Item": {"type": "object", "properties": {"a": {"type": "integer"}}}},
    }
    assert parsed_inputs(schema, {"items": '[{"a": 1}, {"a": 2}]'}) == {
        "items": [{"a": 1}, {"a": 2}]
    }
