"""Prompts never drift from gemini: each name they cite is gemini's, and shared rules reach all."""

import re

import pytest

from geomind.prompts import Prompt
from geomind.prompts.prompt import role_files
from geomind.tools.gemini.skeleton import module_reference, modules_of

GEOMIND_WORDS = {
    "Capacities",
    "Checks",
    "Costs",
    "Decisions",
    "Delivered",
    "Design",
    "Hello",
    "Route",
    "Schematic",
}
"""Words in backticks that are geomind's own, such as a section of a report."""


def gemini_names():
    """Return the names of gemini 0.6.2's modules and plant classes."""
    import gemini as gm

    return set(gm.modules.names()) | set(gm.plants.names())


@pytest.mark.parametrize("role", sorted(role_files()))
def test_every_class_a_prompt_names_is_gemini_s(role):
    """A module or plant gemini renames or drops fails here, not in a live run."""
    cited = set(re.findall(r"`([A-Z][A-Za-z0-9]+)`", role_files()[role].read_text()))
    assert cited - gemini_names() - GEOMIND_WORDS == set()


@pytest.mark.parametrize("role", sorted(role_files()))
def test_every_role_prompt_ends_with_the_shared_rules(role):
    """Sources, no defaults, units and errors are said once, for all 17 roles."""
    text = Prompt(role).content
    assert "## Rules for every agent" in text and "gemini converts every unit" in text


def test_the_module_reference_is_gemini_s_describe():
    """A well's section lists, its ports and its required parameters come from gemini."""
    text = module_reference(*modules_of("wells"))
    assert "### ProductionWell (wells)" in text and "section_length*" in text
    assert "ports: in bottom_in (brine)" in text


def test_a_list_of_quantities_reads_in_the_form_gemini_takes():
    """A list of quantities reads ``{value: [<number>, ...], unit}`` (gemini request 14).

    gemini 0.6.2 gives ``section_length`` as ``type: array``; the reference and
    ``describe_module`` say the list form.
    """
    import gemini as gm

    from geomind.tools.gemini.skeleton import module_tree

    line = "section_length*: array {value: [<number>, ...], unit} length in"
    assert line in module_reference("ProductionWell")
    described = module_tree(gm.modules.get("ProductionWell")().describe())["parameters"]
    assert any(item.startswith(line) for item in described)
    assert not any("[<number>" in item for item in described if "section_" not in item)


def test_an_unknown_module_is_an_error():
    """A name gemini does not have cannot reach a prompt."""
    with pytest.raises(Exception):
        module_reference("NoSuchModule")
