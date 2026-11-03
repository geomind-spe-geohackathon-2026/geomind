"""The verifier: checks the final design once and records gemini's checks."""

from geomind.agents import Verifier
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Verifier,
        "verifier",
        [
            "check_results",
            "case_changes",
            "read_case",
            "compute_kpis",
            "read_result",
            "update_state",
            "read_skill",
            "read_stored",
            "search_memory",
            "read_memory",
            "write_memory",
            "finish",
        ],
    )
