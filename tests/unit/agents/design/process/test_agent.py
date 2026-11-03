"""The process engineer of the design team."""

import re

from geomind import runtime
from geomind.agents import ProcessEngineer
from tests.unit.agents.structure import check_complete

TOOLS = [
    "read_case",
    "list_plants",
    "read_plant",
    "list_modules",
    "describe_module",
    "build_plant",
    "patch_plant",
    "update_state",
    "read_skill",
    "read_stored",
    "search_memory",
    "read_memory",
    "write_memory",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(ProcessEngineer, "design/process", TOOLS)


def test_it_patches_only_its_own_discipline_and_asks_nobody():
    """Its discipline is ``process``; it has no ``ask_user``: what it cannot settle goes up."""
    agent = ProcessEngineer()
    assert agent.discipline == "process"
    assert "ask_user" not in agent.tools() and "set_case" not in agent.tools()


def test_its_prompt_holds_method_and_no_number_of_a_project():
    """Experience is a starting point only; no number stands in its rules outside code names."""
    text = ProcessEngineer().prompt.content
    rules = text.split("## Rules")[1].split("## Output")[0]
    prose = re.sub(r"`[^`]*`", "", rules)
    assert "starting point only" in rules
    assert not any(character.isdigit() for character in prose)


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_PROCESSENGINEER_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_PROCESSENGINEER_MODEL", raising=False)
    assert runtime.role_models()["processengineer"] is None
    assert "GEOMIND_PROCESSENGINEER_MODEL" in runtime.missing_model_settings()


def test_it_records_the_modules_and_their_owners():
    """Its prompt names ``design.modules`` and ``design.owners`` and every discipline."""
    text = ProcessEngineer().prompt.render()
    assert "design.owners" in text and "design.modules" in text
    assert all(f"`{name}`" in text for name in ("reservoir", "well", "energy", "process"))
