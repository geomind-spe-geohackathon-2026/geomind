"""The smallest case and plant files, read from gemini's public schemas."""

from geomind.tools.gemini.skeleton import case_skeleton, plant_skeleton, skeleton_of


def test_a_constant_is_kept_and_other_leaves_are_named():
    """A ``const`` is the value; a required leaf without one is ``<name>``."""
    schema = {
        "type": "object",
        "required": ["format", "name"],
        "properties": {"format": {"const": 1}, "name": {"type": "string"}},
    }
    assert skeleton_of(schema, "file") == {"format": 1, "name": "<name>"}


def test_the_case_and_plant_skeletons_carry_gemini_s_header():
    """Both hold gemini's ``format`` and ``kind`` and name the rest."""
    assert plant_skeleton() == {"format": 1, "kind": "plant", "name": "<name>"}
    assert case_skeleton()["kind"] == "case"
