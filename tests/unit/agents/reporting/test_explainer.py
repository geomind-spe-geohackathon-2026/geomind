"""The explainer: explains the verified design from the tools and the problem state."""

from geomind.agents import Explainer
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Explainer,
        "explainer",
        [
            "read_plant",
            "read_result",
            "compute_kpis",
            "search_documents",
            "finish",
        ],
    )
