"""The economist: costs a verified design with gemini's economics."""

from geomind.agents import Economist
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Economist,
        "analysis/economist",
        [
            "read_case",
            "compute_kpis",
            "estimate_costs",
            "simulate",
            "compare",
            "run_study",
            "sample_uncertainty",
            "sensitivity",
            "read_result",
            "list_studies",
            "read_study",
            "update_state",
            "read_skill",
            "calculate",
            "run_python",
            "web_search",
            "read_web_page",
            "read_stored",
            "search_memory",
            "read_memory",
            "search_rag",
            "read_knowledge",
            "finish",
        ],
    )
