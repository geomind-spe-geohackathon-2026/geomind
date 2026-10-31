"""The tools over gemini's module catalogue, against real gemini modules."""

import pytest

import geomind as gd
from tests.fixtures.calls import call

TOOLS = gd.tools.gemini
PIPE = {
    "length": "1000 m",
    "inner_diameter": "0.2 m",
    "elevation_change": "0 m",
    "heat_transfer_coefficient": 1.0,
}
PIPE_INLETS = {
    "fluid_in": {"m_dot": 40.0, "T": "80 degC", "p": "10 bar"},
    "air_in": {"m_dot": 0.0, "T": "10 degC", "p": "1 bar"},
}


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


@pytest.fixture(scope="module")
def every_module(gm):
    """Return the result of ``list_modules`` without a category; it describes every module."""
    import asyncio

    return asyncio.run(call(TOOLS.list_modules, {}))


def test_list_modules_names_every_module_with_its_category_and_summary(gm, every_module):
    """Every registered name, in gemini's order, with the category and summary it describes."""
    assert not every_module.is_error
    assert [row["name"] for row in every_module.output] == gm.modules.names()
    assert {row["category"] for row in every_module.output} <= set(gm.modules.categories())
    assert all(set(row) == {"name", "category", "summary"} for row in every_module.output)


async def test_list_modules_of_a_category_is_what_gemini_describes(gm):
    """The rows of one category are gemini's own names and descriptions."""
    result = await call(TOOLS.list_modules, {"category": "wells"})
    expected = [
        {"name": name, "category": "wells", "summary": gm.modules.get(name).describe()["summary"]}
        for name in gm.modules.names("wells")
    ]
    assert result.output == expected


async def test_an_unknown_category_is_gemini_s_problem_with_a_suggestion(gm):
    """The model reads gemini's Problem and the close match."""
    result = await call(TOOLS.list_modules, {"category": "wellz"})
    assert result.is_error
    assert result.output["error"]["suggestions"] == ["wells"]


async def test_describe_module_is_gemini_s_description_unchanged(gm):
    """The description is exactly ``describe()`` of the class."""
    result = await call(TOOLS.describe_module, {"name": "Pipe"})
    assert result.output == gm.modules.get("Pipe").describe()


@pytest.mark.parametrize(
    ("tool", "tool_input"),
    [
        (TOOLS.describe_module, {"name": "Pipee"}),
        (TOOLS.evaluate_module, {"name": "Pipee", "parameters": {}}),
    ],
)
async def test_an_unknown_module_is_unknown_name_with_suggestions(gm, tool, tool_input):
    """A misspelt name is a result the model can fix, never an internal error."""
    result = await call(tool, tool_input)
    problem = result.output["error"]
    assert result.is_error
    assert problem["code"] == "unknown_name"
    assert problem["suggestions"] == ["Pipe"]


async def test_evaluate_module_returns_gemini_s_values_unchanged(gm):
    """Unit strings are accepted, and every number is gemini's Value."""
    result = await call(
        TOOLS.evaluate_module, {"name": "Pipe", "parameters": PIPE, "inlets": PIPE_INLETS}
    )
    expected = gm.evaluate(gm.modules.get("Pipe"), PIPE, PIPE_INLETS, None)
    assert not result.is_error
    assert result.output == expected
    assert result.output["outputs"]["pressure_drop"]["unit"] == "Pa"


async def test_a_missing_inlet_is_gemini_s_problem(gm):
    """A validation error of gemini reaches the model as its Problem."""
    result = await call(TOOLS.evaluate_module, {"name": "Pipe", "parameters": PIPE})
    assert result.is_error
    assert result.output["error"]["code"] != "internal"
    assert "air_in" in result.output["error"]["message"]


def test_evaluate_module_needs_a_name_and_parameters():
    """The model sees which inputs are required."""
    assert TOOLS.evaluate_module.input_schema["required"] == ["name", "parameters"]
