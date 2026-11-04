"""The rule-driven comparison moved under the project lead; ``tests/unit/loops`` runs it."""

from geomind.agents.project.comparison import ComparisonDriver, family_design_lead


def test_a_family_s_design_lead_asks_nobody():
    """A family runs beside the others, so its design lead has no ``ask_user``."""
    assert "ask_user" not in family_design_lead().tools()
    assert ComparisonDriver().tools()["family_design_lead"].runs_beside
