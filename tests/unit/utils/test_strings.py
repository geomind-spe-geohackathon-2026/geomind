"""Names and message pieces."""

from geomind.utils.strings import (
    did_you_mean,
    first_paragraph,
    join_names,
    join_path,
    snake_case,
)


def test_snake_case_keeps_acronyms():
    """Class names become agent names."""
    assert snake_case("DesignLoop") == "design_loop"
    assert snake_case("LLMAgent") == "llm_agent"


def test_first_paragraph_is_one_line():
    """Only the first paragraph survives."""
    assert first_paragraph("One\ntwo.\n\nThree.") == "One two."


def test_join_path_and_names():
    """An empty prefix is the root, and no names read as ``<none>``."""
    assert join_path("", "a") == "a"
    assert join_path("a", "b") == "a.b"
    assert join_names([]) == "<none>"


def test_did_you_mean():
    """A close name gives a suggestion, a distant one nothing."""
    assert did_you_mean("promt", ["prompt"]) == "; did you mean 'prompt'?"
    assert did_you_mean("x", ["prompt"]) == ""
