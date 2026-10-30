"""The JSON Patch subset of the problem state."""

import pytest

from geomind.types.patch import operation_problem

ITEM = {"id": "R3", "text": "Cover peak cooling"}


@pytest.mark.parametrize(
    "change",
    [
        {"op": "add", "path": "/requirements/-", "value": ITEM},
        {"op": "replace", "path": "/assumptions/A1/confirmed", "value": True},
        {"op": "remove", "path": "/questions/Q2"},
        {"op": "replace", "path": "/goal", "value": "heat"},
        {"op": "add", "path": "/design/a~1b", "value": None},
    ],
)
def test_contract_operations_are_valid(change):
    """The examples of the contract pass, and ``null`` is a value."""
    assert operation_problem(change) is None


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ("text", "expected only"),
        ({"op": "add", "path": "/goal", "value": 1, "from": "/x"}, "expected only"),
        ({"op": "move", "path": "/goal"}, "add, replace or remove"),
        ({"op": "add", "path": "goal", "value": 1}, "JSON Pointer"),
        ({"op": "add", "value": 1}, "JSON Pointer"),
        ({"op": "add", "path": "/a~2b", "value": 1}, "JSON Pointer"),
        ({"op": "add", "path": "/other", "value": 1}, "top-level key"),
        ({"op": "replace", "path": "/requirements/-", "value": ITEM}, "ends the path"),
        ({"op": "add", "path": "/requirements/-/x", "value": 1}, "ends the path"),
        ({"op": "add", "path": "/goal"}, "expected a value"),
        ({"op": "remove", "path": "/goal", "value": 1}, "expected a value"),
        ({"op": "add", "path": "/requirements/-", "value": {"text": "x"}}, "needs an id"),
        ({"op": "add", "path": "/requirements/-", "value": 3}, "needs an id"),
    ],
)
def test_other_operations_are_refused(change, message):
    """Each mistake has its own message."""
    assert message in operation_problem(change)
