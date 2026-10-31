"""The tools over gemini's module catalogue: final signatures."""

import pytest

import geomind as gd
from tests.fixtures.stubs import check_stub

TOOLS = gd.tools.gemini


@pytest.mark.parametrize(
    ("tool", "tool_input", "effect"),
    [
        (TOOLS.list_modules, {}, "read"),
        (TOOLS.list_modules, {"category": "wells"}, "read"),
        (TOOLS.describe_module, {"name": "Pipe"}, "read"),
        (TOOLS.evaluate_module, {"name": "Pipe", "parameters": {}}, "compute"),
    ],
)
async def test_the_stubs_say_when_they_come(tool, tool_input, effect):
    """Each has its final signature and a phase."""
    await check_stub(tool, tool_input, effect, "S2b")


def test_evaluate_module_needs_a_name_and_parameters():
    """The model sees which inputs are required."""
    assert TOOLS.evaluate_module.input_schema["required"] == ["name", "parameters"]
