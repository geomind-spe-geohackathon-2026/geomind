"""The energy engineer of the design team."""

import re

from geomind import runtime
from geomind.agents import EnergySystemsEngineer
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
    check_complete(EnergySystemsEngineer, "design/energy", TOOLS)


def test_it_patches_only_its_own_discipline_and_asks_nobody():
    """Its discipline is ``energy``; it has no ``ask_user``: what it cannot settle goes up."""
    agent = EnergySystemsEngineer()
    assert agent.discipline == "energy"
    assert "ask_user" not in agent.tools() and "set_case" not in agent.tools()


def test_its_prompt_holds_method_and_no_number_of_a_project():
    """Experience is a starting point only; no number stands in its rules outside code names."""
    text = EnergySystemsEngineer().prompt.content
    rules = text.split("## Rules")[1].split("## Output")[0]
    prose = re.sub(r"`[^`]*`", "", rules)
    assert "starting point only" in rules
    assert not any(character.isdigit() for character in prose)


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_ENERGYSYSTEMSENGINEER_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_ENERGYSYSTEMSENGINEER_MODEL", raising=False)
    assert runtime.role_models()["energysystemsengineer"] is None
    assert "GEOMIND_ENERGYSYSTEMSENGINEER_MODEL" in runtime.missing_model_settings()


def test_it_computes_nothing_by_hand():
    """#45: no formula or conversion; numbers from the case, gemini, or a named assumption."""
    text = EnergySystemsEngineer().prompt.content
    assert "Compute nothing by hand" in text and "no derived value in a change" in " ".join(
        text.split()
    )


def test_it_names_every_cost_size_gemini_asks_for():
    """A duty, an energy, an ice volume or a pipe capacity: each size gemini 0.6.2 may ask for."""
    text = " ".join(EnergySystemsEngineer().prompt.content.split())
    for name in ("`nominal_duty`", "`energy_capacity`", "`volume`", "`nominal_capacity`"):
        assert name in text
    assert "never by hand" in text
