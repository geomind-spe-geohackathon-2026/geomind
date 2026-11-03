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
            "list_plants",
            "read_plant",
            "list_modules",
            "describe_module",
            "evaluate_module",
            "build_plant",
            "set_ranges",
            "size_plant",
            "list_profiles",
            "read_profile",
            "simulate",
            "read_result",
            "list_studies",
            "read_study",
            "check_results",
            "optimize",
            "run_study",
            "write_module",
            "test_module",
            "update_state",
            "read_skill",
            "read_stored",
            "ask_user",
            "finish",
        ],
    )


def test_a_plant_value_no_file_gives_is_the_designer_s_assumption():
    """Segment 9 asked the user for equipment datasheets instead of choosing their values."""
    from geomind.agents import Designer

    text = Designer().prompt.render()
    assert "A plant value gemini lists as missing" in text
    assert "describe_module" in text and "confirmed: false" in text
