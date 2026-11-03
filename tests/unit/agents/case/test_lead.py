"""The case_lead: sets the case from the project's files and the user's answers."""

from geomind import runtime
from geomind.agents import CaseLead, DesignLead
from tests.unit.agents.structure import check_complete

TOOLS = [
    "geoscientist",
    "list_files",
    "read_rag",
    "search_rag",
    "read_case",
    "describe_case",
    "set_case",
    "save_profile",
    "list_profiles",
    "read_profile",
    "read_stored",
    "search_memory",
    "read_memory",
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
    assert not design_lead & {"set_case", "save_profile", "list_files", "read_rag"}


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

    assert "never the whole case again" in " ".join(CaseLead().prompt.render().split())
    assert "send only" in set_case.description or "send only" in set_case.function.__doc__


def test_it_computes_nothing_and_invents_no_number():
    """#43 and #44: a derived value stays unset for gemini; a value with no source is asked."""
    text = CaseLead().prompt.content
    assert "Compute nothing" in text and "stays unset" in text
    assert "with no number of your own" in text


def test_it_writes_no_number_it_worked_out():
    """#64: a dew point worked out inside a question; the span is copied from the file."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "every number you write, in a question" in text and "a dew point" in text
    assert "from the `span` of the data file's `table`" in text


def test_a_missing_value_is_searched_before_it_is_asked_for():
    """Sahand: files, then the knowledge base, then MCP, and only then the user."""
    text = " ".join(CaseLead().prompt.content.split())
    order = ["the project's files", "the knowledge base:", "`read_mcp`", "only when none"]
    assert [text.index(item) for item in order] == sorted(text.index(item) for item in order)
    assert "Search 3 and 4 for every value the files lack before you ask" in text
    assert "knowledge/cost-sources.csv" in text and "`placeholder`" in text


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
    """The case keys carry their source, the derived ones, and every requirement option.

    The meanings come from ``describe_case``, on demand (Track A).
    """
    text = CaseLead().prompt.render()
    assert "site.reservoir.temperature: {value, unit} [derived]" in text
    assert "`describe_case(path)`" in text
    assert "duration: the total time of the steps" in text and "count: how many units" in text


def test_a_change_reports_the_value_before_as_the_case_showed_it():
    """#62: the case lead said a cap was 200 while the case held 300; it reads before and after."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "before and after it with `read_case`" in text and "never from memory" in text


def test_it_reads_once_asks_once_and_copies_digits():
    """Track A: 12 read_stored calls, three questions for the same values, rounded prices."""
    text = " ".join(CaseLead().prompt.content.split())
    assert "never read it again" in text and "Never ask for it again" in text
    assert "digit for digit" in text and "as few `set_case` calls as you can" in text
    assert "read once with `columns`" in text
