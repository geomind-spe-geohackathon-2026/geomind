"""The tools that read and store plants: final signatures."""

import pytest

import geomind as gd
from tests.fixtures.stubs import check_stub

TOOLS = gd.tools.gemini


@pytest.mark.parametrize(
    ("tool", "tool_input", "effect"),
    [
        (TOOLS.list_plants, {}, "read"),
        (TOOLS.read_plant, {}, "read"),
        (TOOLS.read_plant, {"design": "design/a"}, "read"),
        (TOOLS.build_plant, {"plant": {}, "name": "a"}, "write"),
    ],
)
async def test_the_stubs_say_when_they_come(tool, tool_input, effect):
    """Each has its final signature and a phase."""
    await check_stub(tool, tool_input, effect, "S2b")


@pytest.fixture(scope="module")
def spec():
    """Return gemini's plant schema; importing gemini takes more than one test call's budget."""
    import gemini as gm

    return gm.plants.spec_schema()


def test_build_plant_offers_the_plant_schema_of_gemini(spec):
    """The model fills in gemini's own schema, its definitions at the top so references resolve."""
    offered = TOOLS.build_plant.schema()["input_schema"]
    assert offered["properties"]["plant"]["properties"] == spec["properties"]
    assert offered["$defs"].items() >= spec.get("$defs", {}).items()
    assert "$defs" not in offered["properties"]["plant"]
