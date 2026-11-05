"""The well engineer of the design team."""

import re

from geomind import runtime
from geomind.agents import WellEngineer
from tests.unit.agents.structure import check_complete

TOOLS = [
    "describe_module",
    "search_knowledge",
    "read_knowledge",
    "search_memory",
    "read_memory",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(WellEngineer, "design/well", TOOLS)


def test_it_patches_only_its_own_discipline_and_asks_nobody():
    """Its discipline is ``well``; it has no ``ask_user``: what it cannot settle goes up."""
    agent = WellEngineer()
    assert agent.discipline == "well"
    assert "ask_user" not in agent.tools() and "set_case" not in agent.tools()


def test_its_prompt_holds_method_and_no_number_of_a_project():
    """Experience is a starting point only; no number stands in its rules outside code names."""
    text = WellEngineer().prompt.content
    rules = text.split("## Rules")[1].split("## Output")[0]
    prose = re.sub(r"`[^`]*`", "", rules)
    assert "starting point only" in rules
    assert not any(character.isdigit() for character in prose)


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_WELLENGINEER_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_WELLENGINEER_MODEL", raising=False)
    assert runtime.role_models()["wellengineer"] is None
    assert "GEOMIND_WELLENGINEER_MODEL" in runtime.missing_model_settings()


def test_it_computes_nothing_by_hand():
    """#45: no formula or conversion; numbers from the case, gemini, or a named assumption."""
    text = WellEngineer().prompt.content
    assert "Compute nothing by hand" in text and "no derived value in a change" in " ".join(
        text.split()
    )


def test_it_knows_the_form_of_a_well_path_s_section_lists():
    """#74: eight evaluate_module calls failed on section lists, which gemini calls numbers."""
    text = " ".join(WellEngineer().prompt.render().split())
    assert '`{"value": [500, 2000], "unit": "m"}`, never a list of quantities' in text
    assert "`correction_factors` is a plain pair" in text


def test_qa_321_the_riser_and_the_well_share_the_whole_path():
    """QA-321: a riser and a well given each its own part ran a shorter producer."""
    text = " ".join(WellEngineer().prompt.render().split())
    assert "The riser and the well share the WHOLE path" in text


def test_equipment_values_come_from_the_equipment_catalogue_first():
    """Design lead and engineers cite a row of knowledge/data-equipment.csv before a datasheet."""
    from geomind.agents import DesignLead, EnergySystemsEngineer

    for agent in (DesignLead(), EnergySystemsEngineer(), WellEngineer()):
        text = " ".join(agent.prompt.render().split())
        assert "first the row of `knowledge/data-equipment.csv`" in text, agent.name
        assert "cited by its row id" in text


def test_qa_357_well_paths_are_left_to_gemini():
    """QA-357: stated paths stayed at 2500 m while the depth search moved to 2875 m."""
    text = " ".join(WellEngineer().prompt.render().split())
    assert "Leave the section lists of `well`, `riser` and `injector` out" in text
