"""The economist: costs a verified design with gemini's economics."""

from geomind.agents import Economist
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Economist,
        "economist",
        [
            "compute_kpis",
            "estimate_costs",
            "compare",
            "sample_uncertainty",
            "sensitivity",
            "read_result",
            "update_state",
            "read_skill",
            "finish",
        ],
    )
