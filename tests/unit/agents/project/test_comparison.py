"""The rule-driven comparison moved under the project lead; ``tests/unit/loops`` runs it."""

from geomind.agents.project.comparison import ComparisonDriver, family_design_lead


def test_a_family_s_design_lead_asks_nobody():
    """A family runs beside the others, so its design lead has no ``ask_user``."""
    assert "ask_user" not in family_design_lead().tools()
    assert ComparisonDriver().tools()["family_design_lead"].runs_beside


def test_a_failed_or_infeasible_family_is_run_again_within_the_retries():
    """QA-251: a family whose run failed gets one repair run with its reason, then no more."""
    import json
    from types import SimpleNamespace

    from geomind.agents.project.drivers import MARK

    design = {
        "alternatives": [
            {"family": "a", "verdict": "feasible", "design": "design/a", "result": "result/a"},
            {"family": "b", "verdict": "infeasible", "reason": "365 of 365 steps failed"},
        ]
    }
    driver = ComparisonDriver()
    driver._retries = 1
    move = driver.repair(SimpleNamespace(messages=[]), design, {"round": 1}, 3)
    note = json.loads(move.text.removeprefix(MARK))
    assert note["retry"] == "b" and note["attempt"] == 1
    assert note["failed"] == "365 of 365 steps failed"
    kept = move.tool_calls[0].input["changes"][0]["value"]
    assert [item["family"] for item in kept] == ["a"]
    done = SimpleNamespace(role="assistant", content=move.text)
    assert driver.repair(SimpleNamespace(messages=[done]), design, {"round": 1}, 4) is None
    driver._retries = 0
    assert driver.repair(SimpleNamespace(messages=[]), design, {"round": 1}, 3) is None


def test_a_family_run_is_told_to_repair_before_it_records_infeasible():
    """QA-251, QA-253: the family's task asks for repair rounds and never narrows a range."""
    from geomind.agents.project.comparison import family_task

    task = family_task("Compare.", {"id": "b", "summary": "absorption"})
    assert "up to two repair rounds" in task
    assert "never narrow the range" in task
