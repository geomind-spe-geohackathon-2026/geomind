"""The design_lead: sizes, simulates, checks and optimises a design."""

from geomind.agents import DesignLead
from tests.unit.agents.structure import check_complete

TOOLS = [
    "process_engineer",
    "integration_engineer",
    "reservoir_engineer",
    "well_engineer",
    "energy_systems_engineer",
    "fill_parts",
    "merge_designs",
    "read_case",
    "list_plants",
    "read_plant",
    "list_modules",
    "describe_module",
    "evaluate_module",
    "build_plant",
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
    "read_stored",
    "search_memory",
    "read_memory",
    "search_rag",
    "support_lead",
    "ask_user",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(DesignLead, "design/lead", TOOLS)


def test_a_plant_value_no_file_gives_is_the_designer_s_assumption():
    """Segment 9 asked the user for equipment datasheets instead of choosing their values."""
    from geomind.agents import DesignLead

    text = DesignLead().prompt.render()
    assert "A plant value gemini lists as missing" in text
    assert "describe_module" in text and "confirmed: false" in text


def test_it_leads_the_design_team_in_order():
    """Process, then integration, then the three disciplines side by side within the limit."""
    lead = DesignLead()
    tools = lead.tools()
    side = [
        tools[name] for name in ("reservoir_engineer", "well_engineer", "energy_systems_engineer")
    ]
    assert all(item.runs_beside and item.limit == "design_concurrency" for item in side)
    assert not tools["process_engineer"].runs_beside
    assert not tools["integration_engineer"].runs_beside
    text = lead.prompt.render()
    assert text.index("`process_engineer` (the modules") < text.index("then `integration_engineer`")
    assert text.index("then `integration_engineer`") < text.index("then `fill_parts`")
    assert "Send each problem back to its owner" in text


async def test_the_three_disciplines_fill_their_parts_in_one_step():
    """The lead calls the three engineers in one step; each runs as its own nested run."""
    from geomind import runtime
    from tests.fixtures.runs import call, of_type, run, says, uses

    script = [
        uses(
            call("reservoir_engineer", "r", task="Fill the reservoir of design/conn."),
            call("well_engineer", "w", task="Fill the wells of design/conn."),
            call("energy_systems_engineer", "e", task="Fill the energy system of design/conn."),
        ),
        says("reservoir done"),
        says("wells done"),
        says("energy done"),
        says("merged"),
    ]
    with runtime.settings(design_concurrency=3):
        result, _, events = await run(script, agent=DesignLead())
    assert result.status == "done"
    nested = sorted(event.agent for event in of_type(events, "run.started"))
    assert nested == [
        "design_lead",
        "energy_systems_engineer",
        "reservoir_engineer",
        "well_engineer",
    ]


def test_a_case_value_is_never_slipped_into_the_plant():
    """#54: the design lead put a made-up grid gas composition under three plant paths."""
    for name in ("DesignLead", "ProcessEngineer", "ReservoirEngineer", "EnergySystemsEngineer"):
        import geomind.agents as agents

        text = getattr(agents, name)().prompt.content
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
        says("reservoir done"),
        says("wells done"),
        says("energy done"),
        says("merged"),
    ]
    with runtime.settings(design_concurrency=3):
        result, _, events = await run(script, agent=DesignLead())
    nested = sorted(event.agent for event in of_type(events, "run.started"))[1:]
    assert nested == ["energy_systems_engineer", "reservoir_engineer", "well_engineer"]
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


def test_one_family_unless_a_comparison_is_asked():
    """The first end-to-end run designed two families for a request that compared nothing."""
    text = " ".join(DesignLead().prompt.content.split())
    assert "Design one family" in text and "not one design per family" in text


def test_a_superstructure_is_searched_with_the_case_s_objectives():
    """The lead calls evolve_structure with the objectives of the case or its brief only."""
    text = DesignLead().prompt.content
    assert "`evolve_structure` on the merged design" in text
    assert "never ones you choose" in text
