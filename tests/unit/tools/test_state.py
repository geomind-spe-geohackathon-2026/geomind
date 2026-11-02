"""The tool that writes the problem state."""

import pytest

from geomind.tools import update_state
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession


def test_update_state_is_a_write_that_a_crash_cannot_repeat():
    """A rerun would apply the patch twice; a replay reruns it, over its own log."""
    assert update_state.effect == "write"
    assert update_state.idempotent is False
    assert update_state.replays is True


def test_the_schema_hides_the_context():
    """The model sees only the changes."""
    assert list(update_state.input_schema["properties"]) == ["changes"]


def test_the_schema_types_the_operations():
    """The op is an enum, the path has the allowed roots and value names the state's item shapes."""
    items = update_state.schema()["input_schema"]["properties"]["changes"]["items"]
    assert items["properties"]["op"] == {"enum": ["add", "replace", "remove"]}
    assert "results" in items["properties"]["path"]["pattern"]
    assert "case" not in items["properties"]["path"]["pattern"]
    assert "$defs" not in update_state.schema()["input_schema"]
    value = items["properties"]["value"]["description"]
    for root in ("requirements", "assumptions", "results", "questions"):
        assert f"{root} item {{" in value
    assert "'summary': 'string', 'reference?'" in value


@pytest.mark.parametrize(
    "change",
    [
        {"op": "replace", "path": "/goal", "value": "Size it"},
        {"op": "add", "path": "/results/-", "value": {"id": "X1", "summary": "ok"}},
        {"op": "replace", "path": "/results/X1", "value": {"id": "X1", "summary": "ok"}},
        {"op": "replace", "path": "/results", "value": []},
        {"op": "remove", "path": "/results/X1"},
        {"op": "replace", "path": "/assumptions/A1/confirmed", "value": True},
        {"op": "add", "path": "/design/plant", "value": "doublet"},
        {"op": "add", "path": "/requirements/-", "value": {"id": "R1", "text": "t"}},
    ],
)
async def test_every_input_that_was_valid_still_reaches_the_state(change):
    """The shape check refuses nothing that the state accepted before."""
    session = StubSession()
    result = await call(update_state, {"changes": [change]}, session)
    assert result.is_error is False, result.output
    assert session.changes == [[change]]


async def refused(change):
    """Return the error message of the one change that update_state refuses."""
    session = StubSession()
    result = await call(update_state, {"changes": [change]}, session)
    assert result.is_error is True
    assert session.changes == []
    return result.output["error"]["message"]


async def test_a_path_by_position_gives_the_append_form_and_the_shape():
    """Adding at /results/0 or /results/R1 names '/results/-' and the Result shape."""
    message = await refused(
        {"op": "add", "path": "/results/0", "value": {"id": "R", "summary": "s"}}
    )
    assert "'/results/-'" in message
    assert "'id': 'string'" in message and "'summary': 'string'" in message
    assert "'reference?': 'string | null'" in message


async def test_a_value_of_the_wrong_shape_for_an_add_gives_the_shape():
    """A Result without a summary, or a text, is refused with the Result shape."""
    message = await refused({"op": "add", "path": "/results/-", "value": {"id": "R1", "text": "x"}})
    assert "summary" in message and "Result" in message
    message = await refused({"op": "add", "path": "/results/-", "value": "found it"})
    assert "is not an object" in message and "Result {" in message


async def test_a_value_of_the_wrong_shape_for_a_replace_or_an_index_gives_the_shape():
    """Replacing /results with one item, or an item with a text, says what each holds."""
    message = await refused(
        {"op": "replace", "path": "/results", "value": {"id": "R1", "summary": "s"}}
    )
    assert "value is not a list" in message and "'/results/-'" in message
    message = await refused({"op": "replace", "path": "/results/R1", "value": {"id": "R1"}})
    assert "summary" in message and "'/results/R1'" in message
    message = await refused({"op": "replace", "path": "/results/R1/text", "value": "x"})
    assert "not a field of Result" in message and "'summary': 'string'" in message


async def test_a_goal_that_is_not_text_gives_the_shape():
    """The goal is a string."""
    assert "a string for '/goal'" in await refused({"op": "replace", "path": "/goal", "value": 3})


async def test_a_typed_design_key_takes_its_shape_from_the_state_model(monkeypatch):
    """Once ProblemState types a key of design, a value of another shape is refused with it."""
    import pydantic

    from geomind.context import state as state_module
    from geomind.tools import state as tool_state

    class Typed(pydantic.BaseModel):
        reference: str | None = None

    field = pydantic.fields.FieldInfo(annotation=Typed)
    monkeypatch.setitem(tool_state.ProblemState.model_fields, "design", field)
    assert state_module.ProblemState is tool_state.ProblemState
    message = await refused({"op": "replace", "path": "/design/reference", "value": {"a": 1}})
    assert "'/design/reference' to hold string | null" in message
    ok = await call(
        update_state,
        {"changes": [{"op": "replace", "path": "/design/reference", "value": "result/x"}]},
        StubSession(),
    )
    assert ok.is_error is False
