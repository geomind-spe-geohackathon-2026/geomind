"""The project lead: plans the teams' work, routes failures, decides the end."""

import re

from geomind import runtime
from geomind.agents import ProjectLead
from geomind.agents.project.lead.review import Review
from geomind.stores import MemoryWorkspace
from tests.fixtures.cases import example_case
from tests.fixtures.runs import call, context, engine_for, of_type, run, says, uses
from tests.unit.agents.structure import check_complete

TOOLS = [
    "case_lead",
    "design_lead",
    "reviewer",
    "analysis_lead",
    "explainer",
    "support_lead",
    "comparison",
    "read_case",
    "set_case",
    "case_changes",
    "accept_case",
    "update_state",
    "ask_user",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(ProjectLead, "project/lead", TOOLS)


def test_its_reviewer_runs_gemini_s_check_in_code():
    """The reviewer tool is the review with gemini's verdict after it, not a bare delegate."""
    assert isinstance(ProjectLead().tools()["reviewer"], Review)


def test_its_comparison_never_waits_for_a_user():
    """The comparison runs the rule driver with the settings and no user inside it."""
    with runtime.settings(compare_concurrency=2, compare_retries=1):
        driver = ProjectLead().tools()["comparison"].agent
    assert (driver._concurrency, driver._retries, driver._asks) == (2, 1, False)


def test_its_prompt_plans_routes_and_stops():
    """Order of the teams, briefs, owners, one question, never loosening, the stop rules."""
    text = ProjectLead().prompt.content
    order = [
        "(`case_lead`)",
        "(`design_lead`",
        "(`reviewer`)",
        "(`analysis_lead`)",
        "(`explainer`)",
    ]
    assert [text.index(item) for item in order] == sorted(text.index(item) for item in order)
    for words in ("Never loosen the case", "one question with options", "repeated_failure"):
        assert words in text
    rules = text.split("## Rules")[1].split("## Output")[0]
    assert not re.search(r"\d", re.sub(r"`[^`]*`", "", rules))


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_PROJECTLEAD_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_PROJECTLEAD_MODEL", raising=False)
    assert runtime.role_models()["projectlead"] is None
    assert "GEOMIND_PROJECTLEAD_MODEL" in runtime.missing_model_settings()


async def test_the_project_s_case_file_is_loaded_by_rule_first():
    """With a project case and no case in the state, the first move is code, not the model."""
    workspace = MemoryWorkspace(cases={"p": example_case("hackathon_2026")})
    engine = engine_for([says("planned")], workspace=workspace)
    start = context(project="p")
    result = await engine.run(ProjectLead(), start)
    events = engine.store.load_events(start.run_id)
    calls = [event for event in of_type(events, "tool.started") if event.agent == "project_lead"]
    assert calls[0].tool == "set_case" and calls[0].input == {"source": "project"}
    assert result.answer == "planned"


async def test_without_a_project_case_the_model_plans_from_the_start():
    """No case file: the model's first call is its own."""
    script = [uses(call("update_state", "u", changes=[])), says("done")]
    _, _, events = await run(script, agent=ProjectLead())
    first = of_type(events, "tool.started")[0]
    assert first.tool == "update_state"
