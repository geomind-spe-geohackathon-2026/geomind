"""The sample agent."""

import re

import pytest

from geomind import runtime
from geomind.agents import AnalysisLead
from geomind.engine import Context
from geomind.prompts.prompt import SHARED_TOOLS, role_files
from tests.unit.agents.structure import HEADINGS, headings, named_tools


def test_it_declares_the_tools_it_needs():
    """The case, the gemini catalogue, plants, profiles, runs, results, documents, state, answer."""
    assert list(AnalysisLead().tools()) == [
                                               "economist",
                                               "list_files",
                                               "read_rag",
                                               "read_case",
                                               "set_case",
                                               "ask_economics",
                                               "list_modules",
                                               "describe_module",
                                               "evaluate_module",
                                               "list_plants",
                                               "read_plant",
                                               "list_profiles",
                                               "read_profile",
                                               "save_profile",
                                               "simulate",
                                               "read_result",
                                               "list_studies",
                                               "read_study",
                                               "compute_kpis",
                                               "search_rag",
                                               "read_knowledge",
                                               "update_state",
                                               "read_skill",
                                               "calculate",
                                               "run_python",
                                               "web_search",
                                               "read_web_page",
                                               "read_stored",
                                               "search_memory",
                                               "read_memory",
                                               "support_lead",
                                               "ask_user",
                                               "finish",
                                           ]


def test_its_model_is_its_own_role_setting():
    """``GEOMIND_ANALYSISLEAD_MODEL`` names it; there is no default model."""
    assert AnalysisLead().model.resolved_name() == runtime.get("analysislead_model")
    with runtime.settings(analysislead_model=None):
        assert AnalysisLead().model.resolved_name() is None
    with runtime.settings(analysislead_model="fake/strong"):
        assert AnalysisLead().model.resolved_name() == "fake/strong"


def test_its_prompt_fills_every_heading():
    """It is the reference for the others."""
    text = role_files()["analysis/lead"].read_text()
    assert headings(text) == HEADINGS
    sections = re.split(r"^## .*$", text, flags=re.MULTILINE)[1:]
    assert all(len(section.strip().splitlines()) >= 1 for section in sections)
    assert len(text.splitlines()) > 30


def test_its_prompt_names_only_tools_it_has():
    """A model is never told about a tool it cannot call."""
    text = role_files()["analysis/lead"].read_text()
    named = named_tools(text)
    assert sorted(set(named)) == sorted(set(AnalysisLead().tools()) - set(SHARED_TOOLS))


def test_the_system_prompt_lists_the_skills_by_name():
    """Names and one line each, not the skill itself."""
    system = Context().messages_for(AnalysisLead())[0].content
    assert "- gemini-units: Units gemini accepts" in system
    assert "metres, kilograms" not in system


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def test_the_units_skill_names_only_units_gemini_knows(gm):
    """Every unit the skill says works is one ``gm.units`` knows, and each it rules out is not."""
    skills = role_files()["analysis/lead"].parents[2] / "skills"
    text = (skills / "gemini-units" / "SKILL.md").read_text()
    works, fails = re.search(r"These work: (.*?)\. These do not: (.*?)\.", text, re.S).groups()
    known = set(gm.units.names())
    assert all(unit in known for unit in re.findall(r"`([^`]+)`", works))
    assert not any(unit in known for unit in re.findall(r"`([^`]+)`", fails))


def test_an_answer_to_the_user_has_no_raw_improvement_lines_or_ids():
    """QA-300: a comparison ended with raw ``improvement:`` lines and ``finding F84842168``."""
    text = role_files()["analysis/lead"].read_text()
    assert "In an answer to the user, write them as a short list" in text
    assert "Never print an internal id" in text
    assert "HICP" in text


def test_qa_334_a_unit_is_looked_for_under_its_function_before_it_is_called_missing():
    """QA-334: list_modules(category='cooling') was read as 'no compression chiller'."""
    from geomind.agents import AnalysisLead

    text = " ".join(AnalysisLead().prompt.content.split())
    assert "An electric (vapour-compression) chiller is a `HeatPump` in cooling mode" in text


def test_qa_347_a_variant_to_simulate_goes_back_as_a_design_change_never_to_support():
    """QA-347: the analysis lead asked the design lead through support_lead, which reaches none."""
    text = " ".join(AnalysisLead().prompt.content.split())
    assert "`design change needed: <the variant>: <why>`" in text
    assert "never ask for it through `support_lead`" in text
    assert "Never paste a tool's error into your answer" in text
