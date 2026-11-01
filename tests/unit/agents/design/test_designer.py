"""The designer: sizes, simulates, checks and optimises a design."""

from geomind.agents import Designer
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        Designer,
        "designer",
        [
            "read_case",
            "set_case",
            "save_profile",
            "list_plants",
            "read_plant",
            "list_modules",
            "describe_module",
            "evaluate_module",
            "build_plant",
            "size_plant",
            "list_profiles",
            "read_profile",
            "simulate",
            "read_result",
            "check_results",
            "optimize",
            "search_documents",
            "update_state",
            "read_skill",
            "ask_user",
            "finish",
        ],
    )
