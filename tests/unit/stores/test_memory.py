"""The shared memory: experience only, past designs alike to the case and lessons."""

import pytest

from geomind.errors import ToolError
from geomind.stores.memory import FileMemory, MemoryMemory, search_experience, similarity

PAST = {"id": "e1", "features": {"heating_peak": 3e6}, "design": "design/a"}
CASE = {"heating_peak": 3e6, "heating_supply": 338.15, "depth": 1300.0, "step": 3600.0}


def test_a_file_memory_keeps_the_last_entry_of_each_id(tmp_path):
    """Entries outlive the process; a later write of an id replaces the earlier."""
    memory = FileMemory(tmp_path / "memory")
    memory.add("experience", PAST)
    memory.add("experience", {**PAST, "design": "design/b"})
    entries = FileMemory(tmp_path / "memory").entries("experience")
    assert [entry["design"] for entry in entries] == ["design/b"]


def test_knowledge_is_no_section_of_the_memory():
    """Cited values left the memory for the knowledge base; only experience is a section."""
    with pytest.raises(ToolError, match="experience"):
        MemoryMemory().entries("knowledge")


def test_a_recalled_design_is_not_offered_for_a_clearly_different_case():
    """A small shallow heating case does not recall a deep heating and cooling one."""
    deep = {"heating_peak": 3e7, "cooling_peak": 1e7, "heating_supply": 373.15, "depth": 2500.0}
    memory = MemoryMemory(experience=[{"id": "e1", "features": deep}])
    assert similarity(CASE, deep) < 0.6
    assert search_experience(memory, CASE, threshold=0.8) == []
    [alike] = search_experience(
        MemoryMemory(experience=[{"id": "e2", "features": CASE}]), CASE, threshold=0.8
    )
    assert alike["similarity"] == 1.0


def test_a_lesson_holds_method_and_no_number():
    """A digit in a lesson is refused; a user fact may hold one, as the user said it."""
    import pytest

    from geomind.errors import ToolError
    from geomind.stores.memory import checked_lesson

    lesson = {"id": "l1", "kind": "lesson", "role": "design_lead", "origin": {"source": "x"}}
    assert checked_lesson({**lesson, "text": "review coupled values before sizing"})
    with pytest.raises(ToolError, match="no number"):
        checked_lesson({**lesson, "text": "use 3 doublets"})
    assert checked_lesson({**lesson, "kind": "user_fact", "text": "reads 2 decimals"})


def test_lessons_come_by_role_and_never_as_designs():
    """A role reads its own lessons, ``all`` and the user's facts; designs ignore lessons."""
    from geomind.stores.memory import MemoryMemory, lessons_for, search_experience

    memory = MemoryMemory(
        experience=[
            {"id": "a", "kind": "lesson", "role": "design_lead", "text": "x"},
            {"id": "b", "kind": "lesson", "role": "case_lead", "text": "y"},
            {"id": "c", "kind": "lesson", "role": "all", "text": "z"},
            {"id": "d", "kind": "user_fact", "role": "all", "text": "w"},
        ]
    )
    assert [entry["id"] for entry in lessons_for(memory, "design_lead")] == ["a", "c", "d"]
    assert search_experience(memory, {}, 0.0) == []
