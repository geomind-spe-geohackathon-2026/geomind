"""The reviewer: checks the final design once and records gemini's checks."""

from geomind.agents import Reviewer
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Reviewer,
        "project/reviewer",
        [
            "check_results",
            "case_changes",
            "read_case",
            "compute_kpis",
            "read_result",
            "update_state",
            "read_skill",
            "calculate",
            "run_python",
            "web_search",
            "read_web_page",
            "read_stored",
            "search_rag",
            "read_knowledge",
            "finish",
        ],
    )


def test_it_reads_knowledge_only_never_experience():
    """The reviewer checks from scratch: cited values yes, past designs no, and it writes none."""
    tools = Reviewer().tools()
    assert "search_rag" in tools
    assert not {"search_memory", "read_memory"} & set(tools)


def test_qa_187_it_stops_once_the_verdict_is_in_hand():
    """QA-187: check, changes and KPIs in one step, record, finish; no module reads on a pass."""
    from geomind.agents.project.reviewer import Reviewer

    text = " ".join(Reviewer().prompt.content.split())
    assert "Your calls, and no others" in text and "With the verdict in hand you stop" in text
