"""The geoscientist: reads the reports and proposes the ground, reservoir, brine and gas data."""

import pytest

from geomind import runtime
from geomind.agents import CaseLead, Geoscientist
from geomind.agents.case.geoscientist import Findings
from geomind.errors import OutputError
from tests.unit.agents.structure import check_complete

TOOLS = [
    "describe_case",
    "search_knowledge",
    "read_knowledge",
    "search_memory",
    "read_memory",
    "finish",
]
FINDINGS = {
    "values": [
        {
            "quantity": "reservoir mid depth",
            "path": "site.reservoir.reference_depth",
            "base": 2500,
            "low": 2300,
            "high": 2700,
            "unit": "m",
            "quality": "interpreted",
            "source": {"file": "report.pdf", "page": 12, "table": "Table 3"},
        }
    ],
    "missing": [{"quantity": "CO2 fraction", "path": None, "why": "sets the gas handling"}],
    "disagreements": [],
    "files_read": ["report.pdf"],
}


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(Geoscientist, "case/geoscientist", TOOLS)


def test_it_proposes_and_never_sets_the_case():
    """Only the case lead sets the case; the geoscientist reads files and the case."""
    tools = set(Geoscientist().tools())
    assert not tools & {"read_rag", "read_case", "list_files", "search_rag"}
    assert not tools & {"set_case", "save_profile", "update_state", "ask_user"}


def test_the_case_lead_asks_it_as_a_tool():
    """The case lead has its geoscientists as a team and always splits the case (QA-140)."""
    lead = CaseLead()
    team = lead.tools()["geoscientists"]
    assert type(team.members["geoscientist"].agent) is Geoscientist
    assert "geoscientist" not in lead.tools()
    assert "ALWAYS split" in lead.prompt.render()


def test_its_findings_carry_page_quality_and_range():
    """A finding validates with its source; one without a quality or a source is refused."""
    assert Geoscientist().output.validate(FINDINGS)["values"][0]["source"]["page"] == 12
    broken = {**FINDINGS, "values": [{"quantity": "x", "base": 1}]}
    with pytest.raises(OutputError):
        Geoscientist().output.validate(broken)
    assert set(Findings.model_fields) == {"values", "missing", "disagreements", "files_read"}


def test_its_prompt_forbids_typical_values_and_asks_for_transmissivity():
    """Gaps are reported missing, and flow capacity is transmissivity, not permeability alone."""
    text = Geoscientist().prompt.render()
    assert "never fill a gap with a typical value" in text
    assert "transmissivity" in text and "GWR" in text and "CO2" in text and "CH4" in text
    assert "salinity" in text


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_GEOSCIENTIST_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_GEOSCIENTIST_MODEL", raising=False)
    assert runtime.role_models()["geoscientist"] is None
    assert "GEOMIND_GEOSCIENTIST_MODEL" in runtime.missing_model_settings()


async def test_the_case_lead_reads_the_findings_of_a_nested_run():
    """The case lead asks the geoscientist; the nested run finishes with typed findings."""
    import json

    from tests.fixtures.runs import call, of_type, run, says, uses

    script = [
        uses(
            call(
                "geoscientists",
                "g1",
                briefs=[{"role": "geoscientist", "task": "Reservoir and brine: text ..."}],
            )
        ),
        uses(call("finish", "f1", answer=json.dumps(FINDINGS))),
        says("Proposed: reservoir mid depth 2500 m from report.pdf page 12."),
    ]
    result, _, events = await run(script, agent=CaseLead())
    assert result.status == "done"
    nested = [event.agent for event in of_type(events, "run.started")]
    assert nested == ["case_lead", "geoscientist"]
    output = next(e for e in of_type(events, "tool.result") if e.tool == "geoscientists").output
    answers = output if isinstance(output, dict) else json.loads(output)
    found = answers["Geoscientist I"]
    found = found if isinstance(found, dict) else json.loads(found)
    assert found["values"][0]["source"]["page"] == 12
    started = [e for e in of_type(events, "run.started") if e.agent == "geoscientist"]
    assert started[0].instance == "Geoscientist I"


def test_a_gap_goes_to_missing_for_the_lead_to_search():
    """IMP-025: the geoscientist reads no file; the case lead searches what the reports lack."""
    text = " ".join(Geoscientist().prompt.render().split())
    assert "goes in `missing`" in text and "the case lead searches the knowledge base" in text


def test_qa_177_it_reads_the_handbook_and_knows_the_requirement_rules():
    """QA-177: it reads its handbook sections and knows the requirement rules."""
    text = " ".join(Geoscientist().prompt.render().split())
    assert 'read_knowledge("knowledge/handbook-case.md", section=...)' in text
    assert "group IV (requirements) §6.7 and §6.11" in text
    assert "one range = one requirement" in text and "durations vs counts" in text
    assert "has no unit (70 % is `0.7`)" in text and "`when: running`" in text


def test_imp_030_an_assumptions_part_in_the_brief_is_not_read_again():
    """IMP-030: the lead hands each group its part of the assumptions document."""
    text = " ".join(Geoscientist().prompt.render().split())
    assert "never read that document again with `read_knowledge`" in text
