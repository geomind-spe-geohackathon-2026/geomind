"""The rule-driven design moved under the project lead; ``tests/unit/loops`` runs it in loops."""

from geomind.agents.project.drivers import DesignDriver, case_changes_named


def test_the_driver_delegates_to_the_teams_by_their_new_names():
    """Case lead, design lead, reviewer, economist and explainer, as nested runs."""
    tools = DesignDriver().tools()
    assert {"case_lead", "design_lead", "reviewer", "economist", "explainer"} <= set(tools)


def test_a_case_change_line_is_found_in_a_team_s_answer():
    """The line a design lead writes for the case's owner."""
    answer = "done\ncase change needed: site.reservoir: no depth\nnext"
    assert case_changes_named(answer) == ["case change needed: site.reservoir: no depth"]
