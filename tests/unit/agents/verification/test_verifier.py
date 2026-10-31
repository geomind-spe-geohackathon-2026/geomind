"""The verifier: simulates the design afresh and records gemini's checks."""

from geomind.agents import Verifier
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Verifier,
        "verifier",
        [
            "read_plant",
            "simulate",
            "check_results",
            "compute_kpis",
            "read_result",
            "update_state",
            "read_skill",
            "finish",
        ],
    )
