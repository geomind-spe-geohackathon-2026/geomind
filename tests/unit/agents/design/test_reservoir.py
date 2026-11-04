"""The reservoir engineer of the design team."""

import re

from geomind import runtime
from geomind.agents import ReservoirEngineer
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
    "search_rag",
    "finish",
]


def test_it_is_complete():
    """Its tools in order, every heading of its prompt filled, and only its tools named."""
    check_complete(ReservoirEngineer, "design/reservoir", TOOLS)


def test_it_patches_only_its_own_discipline_and_asks_nobody():
    """Its discipline is ``reservoir``; it has no ``ask_user``: what it cannot settle goes up."""
    agent = ReservoirEngineer()
    assert agent.discipline == "reservoir"
    assert "ask_user" not in agent.tools() and "set_case" not in agent.tools()


def test_its_prompt_holds_method_and_no_number_of_a_project():
    """Experience is a starting point only; no number stands in its rules outside code names."""
    text = ReservoirEngineer().prompt.content
    rules = text.split("## Rules")[1].split("## Output")[0]
    prose = re.sub(r"`[^`]*`", "", rules)
    assert "starting point only" in rules
    assert not any(character.isdigit() for character in prose)


def test_its_model_is_its_own_required_setting(monkeypatch):
    """``GEOMIND_RESERVOIRENGINEER_MODEL`` has no fallback."""
    monkeypatch.delenv("GEOMIND_RESERVOIRENGINEER_MODEL", raising=False)
    assert runtime.role_models()["reservoirengineer"] is None
    assert "GEOMIND_RESERVOIRENGINEER_MODEL" in runtime.missing_model_settings()


def test_it_computes_nothing_by_hand():
    """#45: no formula or conversion; numbers from the case, gemini, or a named assumption."""
    text = ReservoirEngineer().prompt.content
    assert "Compute nothing by hand" in text and "names a missing design value alone" in " ".join(
        text.split()
    )


def test_it_leaves_the_reservoir_values_to_gemini():
    """Request 11: gemini 0.6.3 gives the case's reservoir values to each doublet itself."""
    text = " ".join(ReservoirEngineer().prompt.content.split())
    assert "gemini gives them to each doublet, so never set them in the plant" in text
    assert "Take every reservoir and brine value from the case" not in text
