"""The case_lead: sets the case from the project's files and the user's answers."""

from geomind import runtime
from geomind.agents import CaseLead, DesignLead
from tests.unit.agents.structure import check_complete

TOOLS = [
    "geoscientist",
    "list_files",
    "rag_read",
    "rag_search",
    "read_case",
    "set_case",
    "save_profile",
    "list_profiles",
    "read_profile",
    "read_stored",
    "search_memory",
    "read_memory",
    "search_knowledge",
    "update_state",
    "support_lead",
    "ask_user",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(CaseLead, "case/lead", TOOLS)


def test_only_the_formulator_sets_the_case():
    """The design lead reads the case and never sets it or reads the files."""
    design_lead = set(DesignLead().tools())
    assert "set_case" in CaseLead().tools() and "read_case" in design_lead
    assert not design_lead & {"set_case", "save_profile", "list_files", "rag_read"}


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_CASELEAD_MODEL`` has no fallback: without it the role has no model."""
    monkeypatch.delenv("GEOMIND_CASELEAD_MODEL", raising=False)
    assert runtime.role_models()["caselead"] is None
    assert "GEOMIND_CASELEAD_MODEL" in runtime.missing_model_settings()


def test_values_no_file_gives_are_confirmed_in_one_question():
    """Every value not from the files is listed with its source or reason, and the user decides."""
    text = " ".join(CaseLead().prompt.render().split())
    assert "ONE confirmation question" in text
    assert "`approve all`, `change some` and `stop`" in text
    assert "confirmed: true" in text and "price year" in text


def test_the_case_is_set_in_parts():
    """The test run sent the whole case five times; the prompt and set_case say to send parts."""
    from geomind.tools.gemini.case import set_case

    assert "never send the whole case again" in CaseLead().prompt.render()
    assert "send only" in set_case.description or "send only" in set_case.function.__doc__


def test_it_computes_nothing_and_invents_no_number():
    """#43 and #44: a derived value stays unset for gemini; a value with no source is asked."""
    text = CaseLead().prompt.content
    assert "Compute nothing" in text and "stays unset" in text
    assert "propose no number of" in text


def test_time_end_is_exclusive_and_the_data_decides_the_span():
    """#58: the case lead read a year ending on 31 Dec as 364 steps and proposed to drop a day."""
    text = CaseLead().prompt.content
    assert "`time.end` is exclusive" in text and "never the data" in text


def test_it_knows_the_case_format_s_traps():
    """Durations are no counts; supply and return sides; the brine's gas is no grid gas."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "never a `count`" in text and "cooling (chilled water) return is warmer" in text
    assert "Never put one in the other" in text and "Checklist before you hand over" in text


def test_its_key_tree_says_what_each_field_means():
    """The case keys carry their meaning, the derived ones, and every requirement option."""
    text = CaseLead().prompt.render()
    assert "site.reservoir.temperature" in text and "derived from the ground" in text
    assert "duration: the total time of the steps" in text and "count: how many units" in text
