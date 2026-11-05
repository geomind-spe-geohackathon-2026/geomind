"""The one-line sentences of what a call does, shared by the approval cards and the agents."""

from geomind.tools.summaries import DENIED_BY_USER, _differing, _leaf, call_summary


def test_each_summarised_tool_says_what_its_call_does():
    """A plant build, a patch, ranges and a case change each get one sentence; others none."""
    built = call_summary("build_plant", {"name": "p", "plant": {"type": "HeatingPlant"}})
    assert built == "Build plant 'p' of class HeatingPlant."
    patched = call_summary(
        "patch_plant",
        {"design": "design/a", "name": "b", "changes": {"d0": {"depth": {"value": 1}}}},
    )
    assert patched == "Change 1 value(s) of design/a and save it as 'b': d0.depth."
    ranged = call_summary(
        "set_ranges", {"design": "design/a", "name": "r", "ranges": {"depth": {"min": 1, "max": 2}}}
    )
    assert ranged == "Search ranges on design/a, saved as 'r': depth 1 to 2."
    assert call_summary("set_case", {"source": "project"}) == "Load the project's saved case."
    assert call_summary("read_case", {}) is None


def test_the_case_differences_and_a_wordless_denial_have_their_text():
    """The agents read the same helpers the engine does (an agent may not import the engine)."""
    old = {"site": {"ground": {"gradient": {"value": 25, "unit": "°C/km"}}}}
    new = {"site": {"ground": {"gradient": {"value": 30, "unit": "°C/km"}}}}
    assert _differing(old, new) == ["site.ground.gradient"]
    assert _leaf(new, "site.ground.gradient") == "30 °C/km"
    assert DENIED_BY_USER == "denied by the user"
