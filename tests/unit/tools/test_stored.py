"""Results stored by reference: the short form, the outline and the tool that reads them."""

from geomind.engine import Context
from geomind.tools import dispatch, tool
from geomind.tools.stored import (
    INPUT_CHARACTERS,
    is_long,
    outline,
    read_stored,
    reference_of,
    shortened,
    stored_form,
)
from geomind.types import ToolCall
from tests.fixtures.sessions import StubSession


@tool(effect="read")
def plants(context):
    """Return a result with a small list of files and a long mapping."""
    return {
        "project_plants": ["A", "B"],
        "plants": [{"name": f"Class{n}", "summary": "s" * 200} for n in range(30)],
        "capabilities": {f"Class{n}": {"ranges": ["x" * 80] * 20} for n in range(30)},
    }


def call(call_id="c1", **arguments):
    """Return a call of the tool above."""
    return ToolCall(id=call_id, name="plants", input=arguments)


async def test_a_result_over_the_limit_keeps_what_is_small_and_names_the_rest():
    """The model still sees the project's files and every class name; the data is by reference."""
    session = StubSession()
    result = await dispatch(plants, call(), Context(session=session))
    assert result.output["project_plants"] == ["A", "B"]
    assert result.output["reference"] == result.reference == reference_of("c1")
    assert "Class29" in result.output["summary"] and "Class0" in result.output["summary"]
    assert session.artifacts[result.reference]["project_plants"] == ["A", "B"]


async def test_a_mid_size_result_is_whole_with_a_reference():
    """Over the store size and under the limit: whole for the next step, stored for later."""
    session = StubSession()
    result = await dispatch(plants, call(), Context(session=session))
    assert "plants" not in result.output
    from geomind import runtime

    with runtime.settings(tool_result_limit=10_000_000):
        whole = await dispatch(plants, call("c2"), Context(session=session))
    assert whole.output["plants"][0]["name"] == "Class0"
    assert whole.reference == reference_of("c2")
    assert session.artifacts[whole.reference]["plants"][0]["name"] == "Class0"


async def test_a_small_result_is_not_stored():
    """A result under the store size has no reference."""

    @tool(effect="read")
    def small():
        """Return a few characters."""
        return {"a": 1}

    session = StubSession()
    result = await dispatch(
        small, ToolCall(id="s", name="small", input={}), Context(session=session)
    )
    assert result.reference is None and not session.artifacts


def test_outline_shows_a_short_value_whole_and_a_long_list_by_names():
    """Whatever fits is whole; a long list shows its length and names."""
    assert outline({"a": [1, 2]}) == '{"a": [1, 2]}'
    items = [{"name": f"n{k}", "text": "t" * 100} for k in range(40)]
    text = outline(items)
    assert text.startswith("[40 items: n0, n1") and len(text) <= 601


def test_outline_of_a_mapping_with_many_keys_lists_the_keys():
    """Too many keys for the budget: the keys alone."""
    text = outline({f"key{n}": "v" * 100 for n in range(60)})
    assert text.startswith("{60 keys: key0, key1") and len(text) <= 600


def test_stored_form_leaves_a_reserved_key_to_the_outline():
    """An output with its own ``reference`` keeps it inside the summary, nothing is lost."""
    form = stored_form({"reference": "result/x", "summary": {"k": 1}, "big": "b" * 500}, "result-1")
    assert form["reference"] == "result-1" and "result/x" in form["summary"]


async def test_read_stored_returns_the_whole_or_one_part():
    """A path walks keys and list indexes; an unknown one names what exists."""
    session = StubSession()
    await dispatch(plants, call(), Context(session=session))
    context = Context(session=session)
    key = reference_of("c1")
    assert (
        await dispatch(
            read_stored,
            ToolCall(id="r", name="read_stored", input={"reference": key, "path": "plants.1.name"}),
            context,
        )
    ).output == "Class1"
    bad = await dispatch(
        read_stored,
        ToolCall(id="r", name="read_stored", input={"reference": key, "path": "nope"}),
        context,
    )
    assert bad.output["error"]["code"] == "unknown_name"
    missing = await dispatch(
        read_stored,
        ToolCall(id="r", name="read_stored", input={"reference": "result-zzz"}),
        context,
    )
    assert missing.output["error"]["path"] == "reference"


def test_long_call_inputs_are_shortened_and_short_ones_kept():
    """Only an input over the limit changes."""
    short = ToolCall(id="a", name="t", input={"x": 1})
    long = ToolCall(id="b", name="t", input={"x": "y" * (INPUT_CHARACTERS + 1)})
    assert not is_long(short.input) and shortened(short) is short
    assert is_long(long.input) and "shortened" in shortened(long).input
