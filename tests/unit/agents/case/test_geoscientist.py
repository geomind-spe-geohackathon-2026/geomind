"""The geoscientist: reads the reports and proposes the ground, reservoir, brine and gas data."""

import pytest

from geomind import runtime
from geomind.agents import CaseLead, Geoscientist
from geomind.agents.case.geoscientist import Findings
from geomind.errors import OutputError
from tests.unit.agents.structure import check_complete

TOOLS = [
    "list_files",
    "rag_read",
    "rag_search",
    "read_case",
    "read_stored",
    "search_memory",
    "read_memory",
    "search_knowledge",
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
    assert "rag_read" in tools and "read_case" in tools
    assert not tools & {"set_case", "save_profile", "update_state", "ask_user"}


def test_the_case_lead_asks_it_as_a_tool():
    """The case lead has the geoscientist as a delegate and its prompt says when to ask."""
    lead = CaseLead()
    assert type(lead.tools()["geoscientist"].agent) is Geoscientist
    assert "ask the `geoscientist`" in lead.prompt.render()


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
        uses(call("geoscientist", "g1", task="Read report.pdf: reservoir and brine.")),
        uses(call("finish", "f1", answer=json.dumps(FINDINGS))),
        says("Proposed: reservoir mid depth 2500 m from report.pdf page 12."),
    ]
    result, _, events = await run(script, agent=CaseLead())
    assert result.status == "done"
    nested = [event.agent for event in of_type(events, "run.started")]
    assert nested == ["case_lead", "geoscientist"]
    output = next(e for e in of_type(events, "tool.result") if e.tool == "geoscientist").output
    assert json.loads(output)["values"][0]["source"]["page"] == 12
