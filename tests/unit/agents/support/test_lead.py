"""The support lead: routes the other leads' support requests and checks the result."""

from geomind import runtime
from geomind.agents import AnalysisLead, CaseLead, DesignLead, ProjectLead, SupportLead
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(SupportLead, "support/lead", ["summarizer", "curator", "read_stored", "finish"])


def test_every_lead_can_ask_it():
    """The project, case, design and analysis leads each have the ``support_lead`` tool."""
    for lead in (ProjectLead, CaseLead, DesignLead, AnalysisLead):
        assert type(lead().tools()["support_lead"].agent) is SupportLead


def test_it_checks_a_member_s_answer_before_it_goes_back():
    """Its prompt sends a wrong answer back once and adds nothing of its own."""
    text = SupportLead().prompt.content
    assert (
        "send it\n  back once" in text
        or "send it back once" in text
        and "Never add a number" in text
    )


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_SUPPORTLEAD_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_SUPPORTLEAD_MODEL", raising=False)
    assert runtime.role_models()["supportlead"] is None
