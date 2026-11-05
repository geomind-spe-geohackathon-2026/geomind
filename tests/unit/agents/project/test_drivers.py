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


def test_a_requirement_failing_three_rounds_in_a_row_stops_the_loop():
    """IMP-016: one rule failing round after round is reported, not chased."""
    from geomind.agents.project.drivers import stop_answer, stuck_requirements

    assert stuck_requirements([["a", "b"], ["b"], ["b", "c"]]) == ["b"]
    assert stuck_requirements([["a"], ["b"]]) == []
    note = {
        "stop": "requirement_budget",
        "round": 3,
        "design": "design/x",
        "result": "result/y",
        "failures": ["b"],
        "stuck": ["b"],
    }
    assert "b failed in each of the last 3 rounds" in stop_answer(note)


def test_a_passed_design_is_optimised_once():
    """IMP-017: the first pass goes back to the design lead to optimise, only once."""
    from types import SimpleNamespace

    from geomind.agents.project.drivers import MARK, optimise_task, optimised

    assert "optimize" in optimise_task("design/a", "result/b")
    context = SimpleNamespace(messages=[])
    assert optimised(context) is False
    said = SimpleNamespace(role="assistant", content=MARK + '{"optimising": true}')
    assert optimised(SimpleNamespace(messages=[said])) is True


def test_the_project_s_plants_are_used_by_reference_never_retyped(monkeypatch):
    """A stored plant is used by its reference; build_plant only for a new one."""
    from geomind.agents.project import drivers

    monkeypatch.setattr(drivers, "project_plant_names", lambda context: ["HackathonPlant"])
    text = drivers.project_plants_text(None)
    assert "design/<name>" in text and "never build or retype it" in text
    assert "store it with build_plant" not in text
    monkeypatch.setattr(drivers, "project_plant_names", lambda context: [])
    assert drivers.project_plants_text(None) == ""
