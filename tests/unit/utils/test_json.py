"""JSON-safe values and files."""

from pathlib import Path

from geomind.utils.json import append_line, read_json, read_lines, to_jsonable, write_json


def test_to_jsonable_stringifies_unknown_objects():
    """Paths and tuples become JSON values."""
    assert to_jsonable({"path": Path("a"), "items": (1, 2)}) == {"path": "a", "items": [1, 2]}
    assert isinstance(to_jsonable(object()), str)


def test_write_json_creates_folders_and_replaces(tmp_path):
    """The last write wins and no temporary file stays."""
    path = tmp_path / "a/b.json"
    write_json(path, 1)
    write_json(path, {"x": 2})
    assert read_json(path) == {"x": 2}
    assert [item.name for item in path.parent.iterdir()] == ["b.json"]


def test_lines_round_trip_in_order(tmp_path):
    """Lines append, and a missing file reads as empty."""
    path = tmp_path / "log/events.jsonl"
    assert read_lines(path) == []
    append_line(path, 1)
    append_line(path, {"a": 2})
    assert read_lines(path) == [1, {"a": 2}]
