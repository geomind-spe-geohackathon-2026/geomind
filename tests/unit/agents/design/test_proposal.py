"""A design engineer proposes changes; patch_plant takes them as one list."""

from geomind.errors import ToolError
from geomind.tools.gemini.plants import listed_changes


def test_a_change_list_becomes_one_merge_patch_and_a_bad_item_is_named():
    """QA-145: the lead passes every engineer's ``[{path, value, source}]`` in one patch_plant."""
    changes = [
        {"path": "plant.params.d0.depth", "value": {"value": 2500, "unit": "m"}, "source": "case"},
        {"path": "params.backup", "value": "none", "source": "brief"},
    ]
    assert listed_changes(changes) == {
        "params.d0.depth": {"value": 2500, "unit": "m"},
        "params.backup": "none",
    }
    try:
        listed_changes([{"value": 1}])
    except ToolError as error:
        assert error.path == "changes.0"
    else:
        raise AssertionError("an item without a path was accepted")
