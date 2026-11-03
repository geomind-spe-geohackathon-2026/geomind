"""The design_lead: sizes, simulates, checks and optimises a design."""

from geomind.agents import DesignLead
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(
        DesignLead,
        "design/lead",
        [
            "process_engineer",
            "integration_engineer",
            "reservoir_engineer",
            "well_engineer",
            "energy_systems_engineer",
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
            "run_study",
            "update_state",
            "read_skill",
            "read_stored",
            "search_memory",
            "read_memory",
            "write_memory",
            "ask_user",
            "finish",
        ],
    )


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
