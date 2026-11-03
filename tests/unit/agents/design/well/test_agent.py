"""The well engineer of the design team."""

import re

from geomind import runtime
from geomind.agents import WellEngineer
from tests.unit.agents.structure import check_complete

TOOLS = [
    "read_case",
    "read_plant",
    "describe_module",
    "evaluate_module",
    "read_profile",
    "patch_plant",
    "read_stored",
    "search_memory",
    "read_memory",
    "write_memory",
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
