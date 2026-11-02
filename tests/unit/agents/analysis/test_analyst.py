"""The sample agent."""

import re

import pytest

from geomind import runtime
from geomind.agents import Analyst
from geomind.engine import Context
from geomind.prompts.prompt import role_files
from tests.unit.agents.structure import HEADINGS, headings


def test_it_declares_the_tools_it_needs():
    """The case, the gemini catalogue, plants, profiles, runs, results, documents, state, answer."""
    assert list(Analyst().tools()) == [
        "read_case",
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
        "compute_kpis",
        "write_module",
        "test_module",
        "search_documents",
        "update_state",
        "read_skill",
        "ask_user",
        "finish",
    ]


def test_its_model_is_the_role_setting_or_the_default():
    """A strong model by default, chosen per role."""
    assert Analyst().model.resolved_name() == runtime.get("default_model")
    with runtime.settings(analyst_model="fake/strong"):
        assert Analyst().model.resolved_name() == "fake/strong"


def test_its_prompt_fills_every_heading():
    """It is the reference for the others."""
    text = role_files()["analyst"].read_text()
    assert headings(text) == HEADINGS
    sections = re.split(r"^## .*$", text, flags=re.MULTILINE)[1:]
    assert all(len(section.strip().splitlines()) >= 1 for section in sections)
    assert len(text.splitlines()) > 30


def test_its_prompt_names_only_tools_it_has():
    """A model is never told about a tool it cannot call."""
    text = role_files()["analyst"].read_text()
    tools_section = text.split("## Tools")[1].split("## Rules")[0]
    named = re.findall(r"^- `(\w+)`", tools_section, flags=re.MULTILINE)
    assert sorted(named) == sorted(Analyst().tools())


def test_the_system_prompt_lists_the_skills_by_name():
    """Names and one line each, not the skill itself."""
    system = Context().messages_for(Analyst())[0].content
    assert "- gemini-units: Units gemini accepts" in system
    assert "metres, kilograms" not in system


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def test_the_units_skill_names_only_units_gemini_knows(gm):
    """Every unit the skill says works is one ``gm.units`` knows, and each it rules out is not."""
    text = (role_files()["analyst"].parents[1] / "skills" / "gemini-units.md").read_text()
    works, fails = re.search(r"These work: (.*?)\. These do not: (.*?)\.", text, re.S).groups()
    known = set(gm.units.names())
    assert all(unit in known for unit in re.findall(r"`([^`]+)`", works))
    assert not any(unit in known for unit in re.findall(r"`([^`]+)`", fails))
