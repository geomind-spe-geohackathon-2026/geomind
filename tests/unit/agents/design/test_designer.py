"""The designer: proposes design families, builds one design and runs it."""

from geomind.agents import Designer
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Designer,
        "designer",
        [
            "list_plants",
            "read_plant",
            "list_modules",
            "describe_module",
            "evaluate_module",
            "build_plant",
            "list_profiles",
            "read_profile",
            "simulate",
            "read_result",
            "check_results",
            "search_documents",
            "set_brief",
            "update_state",
            "read_skill",
            "ask_user",
            "finish",
        ],
    )
