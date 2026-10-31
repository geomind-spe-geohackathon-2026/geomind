"""The tools that read profiles and run a plant: final signatures."""

import pytest

import geomind as gd
from tests.fixtures.stubs import check_stub

TOOLS = gd.tools.gemini


@pytest.mark.parametrize(
    ("tool", "tool_input", "effect"),
    [
        (TOOLS.list_profiles, {}, "read"),
        (TOOLS.read_profile, {"name": "heating_demand"}, "read"),
        (TOOLS.simulate, {}, "compute"),
        (TOOLS.simulate, {"design": "design/a", "profile": "heating_demand"}, "compute"),
    ],
)
async def test_the_stubs_say_when_they_come(tool, tool_input, effect):
    """Each has its final signature and a phase."""
    await check_stub(tool, tool_input, effect, "S2b")
