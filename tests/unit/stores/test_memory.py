"""The shared memory: sections, cited knowledge and similar experience."""

import pytest

from geomind.errors import ToolError
from geomind.stores.memory import (
    FileMemory,
    MemoryMemory,
    checked_knowledge,
    search_experience,
    search_knowledge,
    similarity,
)

CITED = {
    "id": "k1",
    "item": "Net drilling cost",
    "value": 1000.0,
    "unit": "EUR/m",
    "title": "A drilling survey",
    "publisher": "An agency",
    "year": 2013,
    "page": "26",
    "price_year": 2013,
    "currency": "EUR",
    "status": "verified",
}
CASE = {"heating_peak": 3e6, "heating_supply": 338.15, "depth": 1300.0, "step": 3600.0}


def test_a_file_memory_keeps_the_last_entry_of_each_id(tmp_path):
    """Entries outlive the process; a later write of an id replaces the earlier."""
    memory = FileMemory(tmp_path / "memory")
    memory.add("knowledge", CITED)
    memory.add("knowledge", {**CITED, "value": 1100.0})
    assert [entry["value"] for entry in FileMemory(tmp_path / "memory").entries("knowledge")] == [
        1100.0
    ]


def test_an_unknown_section_is_refused():
    """Only knowledge and experience exist."""
    with pytest.raises(ToolError, match="knowledge, experience"):
        MemoryMemory().entries("notes")


def test_knowledge_needs_its_source_and_money_its_year_and_currency():
    """A value without its source, or a price without its year and currency, is no knowledge."""
    assert checked_knowledge(CITED) == CITED
    with pytest.raises(ToolError, match="title"):
        checked_knowledge({**CITED, "title": ""})
    with pytest.raises(ToolError, match="price_year and currency"):
        checked_knowledge({**CITED, "price_year": None, "currency": None})


def test_knowledge_is_found_by_its_words_with_its_source():
    """A search returns the entry whole, its source and status with it."""
    memory = MemoryMemory(knowledge=[CITED])
    [found] = search_knowledge(memory, "drilling cost")
    assert found["publisher"] == "An agency" and found["status"] == "verified"


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
