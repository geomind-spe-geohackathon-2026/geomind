"""The tools that judge a design: final signatures."""

import pytest

import geomind as gd
from tests.fixtures.stubs import check_stub

TOOLS = gd.tools.gemini


@pytest.mark.parametrize(
    ("tool", "tool_input", "effect", "phase"),
    [
        (TOOLS.check_results, {"reference": "result/a"}, "compute", "S3"),
        (TOOLS.compute_kpis, {"reference": "result/a"}, "compute", "S3"),
        (TOOLS.estimate_costs, {"reference": "result/a"}, "compute", "S3"),
        (TOOLS.test_module, {"path": "module.py"}, "execute", "S3"),
        (
            TOOLS.optimize,
            {"design": "design/a", "variables": {}, "objective": "lcoh"},
            "compute",
            "S4",
        ),
        (
            TOOLS.sample_uncertainty,
            {"design": "design/a", "distributions": {}, "samples": 10, "metrics": ["lcoh"]},
            "compute",
            "S4",
        ),
    ],
)
async def test_the_stubs_say_when_they_come(tool, tool_input, effect, phase):
    """Each has its final signature and a phase."""
    await check_stub(tool, tool_input, effect, phase)
