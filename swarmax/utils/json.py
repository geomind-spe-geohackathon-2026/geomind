"""JSON-safe values and the small file formats of the stores."""

import json
import os
from pathlib import Path

from pydantic_core import to_jsonable_python


def to_jsonable(value):
    """Return ``value`` as JSON-compatible data; unknown objects become their ``str``."""
    return to_jsonable_python(value, fallback=str)


def read_json(path):
    """Return the parsed JSON file at ``path``."""
    return json.loads(Path(path).read_text())


def write_json(path, value):
    """Replace the JSON file at ``path`` atomically, creating its folder."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(json.dumps(value))
    os.replace(temporary, path)


def append_line(path, value):
    """Append one JSON value as a line to the file at ``path``, creating its folder."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value) + "\n")


def read_lines(path):
    """Return every JSON value of a JSON-lines file; a missing file has none."""
    path = Path(path)
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line]
