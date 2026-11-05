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
            "read_knowledge",
            "read_skill",
            "finish",
        ],
    )


def test_it_reads_knowledge_only_for_its_sources():
    """The explainer cites knowledge with its source and never reads past designs."""
    tools = Explainer().tools()
    assert "search_rag" in tools
    assert not {"search_memory", "read_memory"} & set(tools)


def test_it_quotes_gemini_s_explanation_of_a_structure_search():
    """An ``evolve_structure`` study's ``explanation`` and ``table`` are quoted, never computed.

    The rule lives in the ``report`` skill the explainer reads before ``Decisions``.
    """
    from geomind.prompts.prompt import FOLDER

    assert "read_skill('report')" in Explainer().prompt.content
    path = FOLDER.parent / "skills" / "report" / "SKILL.md"
    text = " ".join(path.read_text().split())
    assert "`explanation`" in text and "`table`" in text
    assert "Quote them as they are" in text and "Never compute" in text


def test_qa_218_a_conceptual_question_is_answered_in_a_few_steps():
    """QA-218: other questions skip the design headings; sections are read, never fished for."""
    explainer = Explainer()
    assert "read_knowledge" in explainer.tools()
    text = " ".join(explainer.prompt.content.split())
    assert "answer that question only, under headings that fit it" in text
    assert "never search for a section by its number or title" in text
    assert "at most three searches per answer" in text
