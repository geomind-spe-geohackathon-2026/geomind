"""The formulator: sets the case from the project's files and the user's answers."""

from geomind import runtime
from geomind.agents import Designer, Formulator
from tests.unit.agents.structure import check_complete

TOOLS = [
    "list_files",
    "read_document",
    "search_documents",
    "read_case",
    "set_case",
    "save_profile",
    "list_profiles",
    "read_profile",
    "read_stored",
    "update_state",
    "ask_user",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(Formulator, "formulator", TOOLS)


def test_only_the_formulator_sets_the_case():
    """The designer reads the case and never sets it or reads the files."""
    designer = set(Designer().tools())
    assert "set_case" in Formulator().tools() and "read_case" in designer
    assert not designer & {"set_case", "save_profile", "list_files", "read_document"}


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_FORMULATOR_MODEL`` has no fallback: without it the role has no model."""
    monkeypatch.delenv("GEOMIND_FORMULATOR_MODEL", raising=False)
    assert runtime.role_models()["formulator"] is None
    assert "GEOMIND_FORMULATOR_MODEL" in runtime.missing_model_settings()


def test_values_no_file_gives_are_confirmed_in_one_question():
    """Every value not from the files is listed with its source or reason, and the user decides."""
    text = Formulator().prompt.render()
    assert "ONE confirmation question" in text
    assert "`approve all`, `change some` and `stop`" in text
    assert "confirmed: true" in text and "price year" in text
