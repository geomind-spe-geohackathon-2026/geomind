"""The design_lead: sizes, simulates, checks and optimises a design."""

from geomind.agents import DesignLead
from tests.unit.agents.structure import check_complete

TOOLS = [
            "fill_parts",
            "merge_designs",
            "union_designs",
            "read_case",
            "list_plants",
            "list_starts",
            "start_plant",
            "read_plant",
            "list_modules",
            "describe_module",
            "evaluate_module",
            "build_plant",
            "adopt_design",
            "patch_plant",
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
            "evolve_structure",
            "run_study",
            "update_state",
            "read_skill",
            "calculate",
            "run_python",
            "web_search",
            "read_web_page",
            "read_stored",
            "search_memory",
            "read_memory",
            "search_rag",
            "read_knowledge",
            "support_lead",
            "ask_user",
            "finish",
        ]



def proposed(call_id):
    """Return an engineer's step that finishes with a one-change proposal."""
    import json

    from tests.fixtures.runs import call, uses

    change = {"path": "params.d0.depth", "value": {"value": 2500, "unit": "m"}, "source": "case"}
    return uses(call("finish", call_id, answer=json.dumps({"changes": [change]})))

def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(DesignLead, "design/lead", TOOLS)


def test_a_plant_value_no_file_gives_is_the_designer_s_assumption():
    """Segment 9 asked the user for equipment datasheets instead of choosing their values."""
    from geomind.agents import DesignLead

    text = DesignLead().prompt.render()
    assert "A plant value gemini lists as missing" in text
    assert "describe_module" in text and "confirmed: false" in text


def test_the_lead_alone_writes_and_splits_in_one_team_call():
    """QA-145: the lead builds once, splits into one fill_parts call and patches once."""
    lead = DesignLead()
    tools = lead.tools()
    for name in ("reservoir_engineer", "well_engineer", "process_engineer", "integration_engineer"):
        assert name not in tools
    members = tools["fill_parts"].members
    assert set(members) == {"reservoir_engineer", "well_engineer", "energy_systems_engineer"}
    assert all(item.runs_beside and item.limit == "design_concurrency" for item in members.values())
    text = " ".join(lead.prompt.render().split())
    assert text.index("build it ONCE with `build_plant`") < text.index("call `fill_parts` ONCE")
    assert text.index("call `fill_parts` ONCE") < text.index("ONE `patch_plant`")
    assert "As soon as `missing` is 0" in text


async def test_two_instances_of_one_engineer_fill_their_groups_in_one_step():
    """IMP-025: a list of briefs runs one named instance each, at the same time."""
    from geomind import runtime
    from tests.fixtures.runs import call, of_type, run, says, uses

    briefs = [
        {"role": "reservoir_engineer", "task": "Subsurface and wells: params.d0.* ..."},
        {"role": "reservoir_engineer", "task": "Treatment and gas: degasser ..."},
        {"role": "energy_systems_engineer", "task": "Heating: heat pump, boiler ..."},
    ]
    script = [
        uses(call("fill_parts", "f", briefs=briefs)),
        proposed("f1"),
        proposed("f2"),
        proposed("f3"),
        says("patched"),
    ]
    with runtime.settings(design_concurrency=4):
        result, _, events = await run(script, agent=DesignLead())
    assert result.status == "done"
    output = next(e for e in of_type(events, "tool.result") if e.tool == "fill_parts").output
    assert set(output) == {"Reservoir engineer I", "Reservoir engineer II", "Energy systems engineer I"}


def test_a_case_value_is_never_slipped_into_the_plant():
    """#54: the design lead put a made-up grid gas composition under three plant paths."""
    import geomind.agents as agents

    for name in ("DesignLead", "ReservoirEngineer", "WellEngineer", "EnergySystemsEngineer"):
        text = " ".join(getattr(agents, name)().prompt.content.split())
        assert "never put it into the plant under another path" in text


async def test_fill_parts_runs_the_three_engineers_at_the_same_time():
    """#55: the lead called them one by one; the tool runs every brief as its own nested run."""
    import json

    from geomind import runtime
    from tests.fixtures.runs import call, of_type, run, says, uses

    briefs = {
        "reservoir_engineer": "Fill the reservoir of design/conn.",
        "well_engineer": "Fill the wells of design/conn.",
        "energy_systems_engineer": "Fill the energy system of design/conn.",
    }
    script = [
        uses(call("fill_parts", "f", briefs=briefs)),
        proposed("f1"),
        proposed("f2"),
        proposed("f3"),
        says("merged"),
    ]
    with runtime.settings(design_concurrency=3):
        result, _, events = await run(script, agent=DesignLead())
    nested = sorted(event.agent for event in of_type(events, "run.started"))
    assert nested == ["design_lead", "energy_systems_engineer", "reservoir_engineer", "well_engineer"]
    output = next(e for e in of_type(events, "tool.result") if e.tool == "fill_parts").output
    assert set(output) == set(briefs) and result.answer == "merged"
    assert json.dumps(output)


async def test_fill_parts_refuses_a_brief_for_no_member():
    """A brief for an engineer outside the side-by-side three is named with the members."""
    from tests.fixtures.runs import call, of_type, run, says, uses

    script = [uses(call("fill_parts", "f", briefs={"process_engineer": "x"})), says("ok")]
    _, _, events = await run(script, agent=DesignLead())
    result = next(e for e in of_type(events, "tool.result") if e.tool == "fill_parts")
    assert result.is_error and "reservoir_engineer" in str(result.output)


def test_the_best_family_and_one_alternative_in_one_superstructure():
    """QA-211: one family with one doublet, never searched, ended infeasible on 49 % gas."""
    text = " ".join(DesignLead().prompt.content.split())
    assert "at least one materially different alternative" in text
    assert "not one design per family" in text


def comparing_skill():
    """Return the ``comparing-designs`` skill as one line: the lead reads it for a search."""
    from geomind.prompts.prompt import FOLDER

    path = FOLDER.parent / "skills" / "comparing-designs" / "SKILL.md"
    return " ".join(path.read_text().split())


def test_a_superstructure_is_searched_with_the_case_s_objectives():
    """The lead calls evolve_structure with the objectives of the case or its brief only.

    The rule lives in the ``comparing-designs`` skill the prompt sends the lead to.
    """
    assert "comparing-designs" in DesignLead().prompt.content
    text = comparing_skill()
    assert "`evolve_structure` on the merged design" in text
    assert "never ones you choose" in text


def test_it_quotes_why_the_structure_search_stopped():
    """The search's ``stopped``, ``why``, ``explanation`` and ``table`` are quoted, not computed."""
    text = comparing_skill()
    assert "quoting `stopped` and `why`" in text
    assert "`explanation` and `table`, as gemini gives them, never computed" in text


def test_a_handed_design_it_checks_is_recorded_as_the_final_design():
    """#72: the lead checked a complete design, then wrote it to ``results`` only."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "A design handed to you complete that you simulate and check is final too" in text


def test_stored_plants_are_ranked_in_one_study_never_typed_again():
    """QA-278: a stored plant or version goes in by its reference, all in one run_study."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "build_plant` its `plant`" not in text
    assert "ONE `run_study` over all their references" in text
    assert "never with `build_plant`" in text


def test_an_optimise_request_works_on_that_design_only_and_keeps_a_better_start():
    """QA-276: no unasked family after the optimum; the stored plant wins when it is better."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "works on that design only: no other family" in text
    assert "when the start is as good or better, say so, keep the start" in text


def test_a_failing_requirement_gets_design_changes_never_a_requirement_change():
    """QA-211: the options offered for a failing hard limit are design changes only."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "the options you name are design changes only" in text


def test_a_skill_is_loaded_with_read_skill_never_a_dummy_call():
    """QA-296: no read_web_page on a placeholder URL to load a skill."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "Load a skill with `read_skill`, never with a dummy call" in text


def test_a_report_on_several_plant_versions_compares_them_all():
    """QA-337: a recommendation or report runs one study over every version, not current alone."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "is a comparison: run ONE `run_study` over every version" in text


def test_after_size_the_remaining_issues_go_in_one_patch():
    """QA-343: one patch after size; a closed cooler loop's values are never invented."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "After `size_plant`, patch every value its `issues` name in ONE `patch_plant`" in text


def test_a_long_knowledge_document_is_read_by_its_contents_then_sections():
    """QA-351: contents first, then the sections; never the whole document."""
    import geomind.agents as agents

    for name in ("DesignLead", "ReservoirEngineer", "EnergySystemsEngineer", "WellEngineer"):
        text = " ".join(getattr(agents, name)().prompt.render().split())
        assert "contents first (`read_knowledge` without `section` gives only the contents)" in text


def test_a_brief_quotes_the_handbook_lines_the_member_needs():
    """QA-351: the brief carries the handbook lines with their section; the member reads less."""
    text = " ".join(DesignLead().prompt.render().split())
    assert "Quote the handbook lines a member needs in its brief, with their section number" in text
