"""The files a case names: which they are, and which names are safe.

A case is the content of a ``case.json``. The files it names are the ``file`` of every series
(``data/demand.csv``) and its ``economics`` file name; the economics file may name series files
too, relative to its own folder. A name is a relative path of safe parts: nothing absolute, no
``..``, so a project folder or a run never reads or writes outside itself.
"""

import json
import posixpath


def is_safe_name(name):
    """Tell whether ``name`` is a relative path of plain parts, using ``/`` between them."""
    if not isinstance(name, str) or not name or "\\" in name or "\0" in name:
        return False
    parts = name.split("/")
    return all(part not in ("", ".", "..") for part in parts) and ":" not in parts[0]


def series_files(node):
    """Return the ``file`` names inside a case dict or list, in order."""
    if isinstance(node, list):
        return [name for item in node for name in series_files(item)]
    if not isinstance(node, dict):
        return []
    named = [node["file"]] if isinstance(node.get("file"), str) else []
    return named + [name for item in node.values() for name in series_files(item)]


def case_files(data):
    """Return the names of the files a case dict names: its series and its economics file."""
    economics = data.get("economics")
    named = [economics] if isinstance(economics, str) else []
    return named + series_files({key: value for key, value in data.items() if key != "economics"})


def economics_files(name, content):
    """Return the names of the files that an economics file ``name`` with ``content`` names."""
    try:
        data = json.loads(content)
    except ValueError:
        return []
    folder = posixpath.dirname(name)
    return [posixpath.normpath(posixpath.join(folder, file)) for file in series_files(data)]


def named_files(data, read):
    """Return ``{name: bytes}`` of the files a case dict names that ``read(name)`` finds.

    ``read`` returns the bytes of a name or ``None``. An unsafe name is skipped here; the case
    that names it is refused where it is built.
    """
    files = {}
    queue = case_files(data)
    while queue:
        name = queue.pop(0)
        content = read(name) if name not in files and is_safe_name(name) else None
        if content is None:
            continue
        files[name] = content
        if name == data.get("economics"):
            queue += economics_files(name, content)
    return files
