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


def test_qa_219_159_it_reads_once_and_keeps_what_it_read():
    """QA-219, QA-159: list_studies once, the economics once, no re-read of its own costs."""
    economist = Economist()
    for name in ("read_case", "estimate_costs", "list_studies", "read_study"):
        assert economist.tools()[name].keeps_result
    text = " ".join(economist.prompt.content.split())
    assert "`list_studies` at most once per run" in text and "three steps" in text
