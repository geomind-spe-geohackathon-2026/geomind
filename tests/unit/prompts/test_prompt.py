"""System prompts."""

import pytest

from geomind.errors import UnknownNameError
from geomind.prompts import Prompt


def test_role_loads_its_file():
    """A role loads ``prompts/<team>/<name>.md`` by ``<team>/<name>``."""
    assert "design lead" in Prompt("design/lead").render().lower()


def test_every_role_file_has_its_agent_module():
    """``prompts/<team>/<name>.md`` belongs to ``agents/<team>/<name>.py``."""
    from geomind.prompts.prompt import FOLDER, role_files

    files = role_files()
    assert files
    agents = FOLDER.parent / "agents"
    assert all((agents / f"{role}.py").exists() for role in files)


def test_inline_text():
    """Inline text is stripped and kept."""
    assert Prompt.text("  Be brief.\n").render() == "Be brief."


def test_unknown_role_suggests_a_name():
    """A typo gets a close match."""
    with pytest.raises(UnknownNameError, match="did you mean 'design/lead'"):
        Prompt("design/led")


def test_the_shared_text_names_the_tool_it_is_given_with():
    """The texts added for the shared tools name each tool the shared set holds."""
    from geomind.prompts.prompt import KNOWLEDGE, MEMORY, SHARED_TOOLS, STORED_RESULTS

    assert all(f"`{name}" in STORED_RESULTS + MEMORY + KNOWLEDGE for name in SHARED_TOOLS)


def test_the_well_engineer_sets_the_pump_depth_and_the_lead_sends_it_back():
    """E2E-13: the design lead chose a riser's ``esp_depth`` itself after a refused simulate."""
    well = " ".join(Prompt("design/well").render().split())
    lead = " ".join(Prompt("design/lead").render().split())
    assert "The pump depth is yours." in well
    assert "`riser.esp_depth` both the ESP's `setting_depth`" in well
    assert "the well engineer's: send it back to them" in lead
    assert "Simulate only when `missing` is 0." in lead


def test_an_esp_curve_comes_from_its_source_or_is_asked_never_invented():
    """E2E-15: the design lead patched ``head_coefficients = [1e7, 0, ...]`` with no source.

    The well engineer takes the curves gemini derives from the pump design values or from a
    source, never typed; the lead sends a curve failure back, and asks the user for a curve that
    no source gives.
    """
    well = " ".join(Prompt("design/well").render().split())
    lead = " ".join(Prompt("design/lead").render().split())
    assert "a pump curve) is your assumption" not in well
    assert "never type an ESP's curves" in well and "the failure's `curve`" in well
    assert "never patch an ESP's curves yourself" in lead
    assert "ask the user for the pump's curve" in lead
