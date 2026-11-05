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


def test_stored_families_are_compared_by_one_study_run():
    """QA-278: families that are stored plant versions run as one run_study, not N runs."""
    import json
    from types import SimpleNamespace

    from geomind.agents.project.drivers import MARK

    families = [
        {"id": "v1", "summary": "full cooling", "design": "design/v1"},
        {"id": "v2", "summary": "heat pump", "design": "design/v2"},
    ]
    context = SimpleNamespace(messages=[], problem=SimpleNamespace(design={}))
    driver = ComparisonDriver()
    from geomind.agents.project import comparison

    monkey = comparison.request_of
    comparison.request_of = lambda _: "Compare."
    try:
        move = driver.batch(context, families, {"round": 1}, 2)
    finally:
        comparison.request_of = monkey
    assert len(move.tool_calls) == 1
    task = move.tool_calls[0].input["task"]
    assert "ONE run_study" in task and "['design/v1', 'design/v2']" in task
    note = json.loads(move.text.removeprefix(MARK))
    assert note == {"round": 1, "batch": ["v1", "v2"], "study": True}


def test_a_family_run_reads_the_case_once_and_keeps_its_stored_plant():
    """QA-236: no section-by-section re-read; a stored family is never retyped."""
    from geomind.agents.project.comparison import family_task

    task = family_task("Compare.", {"id": "v3", "summary": "x", "design": "design/v3"})
    assert "read_case at most once" in task
    assert "It is stored as design/v3" in task


def test_qa_278_after_one_study_over_every_version_no_family_runs_again():
    """QA-278 retest: named entries read as other families, then per-family runs and a crash."""
    import json
    from types import SimpleNamespace

    from geomind.agents.project.comparison import has_entry, same_family
    from geomind.agents.project.drivers import MARK

    design = {
        "families": [{"id": "v1", "summary": "full cooling", "design": "design/v1"}],
        "alternatives": [
            {"family": "v1 HeatingFullCoolingPlant", "verdict": "infeasible", "reason": "cold"}
        ],
    }
    assert has_entry(design, "v1") and same_family("v1: plant", "v1")
    assert not same_family("v10", "v1")
    study = SimpleNamespace(
        role="assistant", content=MARK + json.dumps({"round": 1, "batch": ["v1"], "study": True})
    )
    driver = ComparisonDriver()
    driver._retries = 2
    assert driver.repair(SimpleNamespace(messages=[study]), design, {"round": 1}, 3) is None
    calls = [("explainer", "The comparison.")]
    context = SimpleNamespace(messages=[], problem=SimpleNamespace(design=design))
    move = driver.retry(context, calls, {"retry": "w9"}, {"round": 1}, 4)
    assert move.tool_calls[0].name != "family_design_lead"


def test_qa_353_a_denied_family_run_is_never_asked_again(monkeypatch):
    """QA-353: three identical family_design_lead cards after the user denied them with words."""
    import json
    from types import SimpleNamespace

    from geomind.agents.project import comparison, lead
    from geomind.agents.project.drivers import MARK

    words = "No new family run. Compare the families you have now and answer."
    monkeypatch.setattr(
        lead, "request_denials", lambda context: [("family_design_lead", "run", words)]
    )
    design = {
        "families": [{"id": "a", "summary": "x"}, {"id": "b", "summary": "y"}],
        "alternatives": [
            {"family": "a", "verdict": "verified", "design": "design/a", "result": "result/a"},
            {"family": "b", "verdict": "failed", "reason": "denied"},
        ],
    }
    note = SimpleNamespace(
        role="assistant", content=MARK + json.dumps({"round": 1, "batch": ["a"]})
    )
    context = SimpleNamespace(
        session=object(), messages=[note], problem=SimpleNamespace(design=design)
    )
    monkeypatch.setattr(comparison, "request_of", lambda _: "Compare.")
    driver = comparison.ComparisonDriver()
    driver._retries = 2
    move = driver.next_move(context, [("family_design_lead", words)], {"round": 1}, 5)
    assert all(call.name != "family_design_lead" for call in move.tool_calls)
    assert driver.repair(context, design, {"round": 1}, 5) is None
    assert words in comparison.denial_text(comparison.denied_runs(context))
