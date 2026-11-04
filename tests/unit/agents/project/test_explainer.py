"""The explainer: explains the verified design from the tools and the problem state."""

from geomind.agents import Explainer
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Explainer,
        "project/explainer",
        [
            "read_case",
            "case_changes",
            "read_plant",
            "read_result",
            "list_studies",
            "read_study",
            "compute_kpis",
            "estimate_costs",
            "search_rag",
            "finish",
        ],
    )


def test_it_reads_knowledge_only_for_its_sources():
    """The explainer cites knowledge with its source and never reads past designs."""
    tools = Explainer().tools()
    assert "search_rag" in tools
    assert not {"search_memory", "read_memory"} & set(tools)
