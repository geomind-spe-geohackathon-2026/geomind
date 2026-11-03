"""``.env`` files: ``NAME=value`` lines read into the environment, the real environment first."""

import os
import re

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$")


def read_env_file(path):
    """Return ``{name: value}`` of a ``.env`` file; comments and blank lines are skipped."""
    found = {}
    for line in path.read_text().splitlines():
        match = _LINE.match(line)
        if match is None or line.lstrip().startswith("#"):
            continue
        value = match[2]
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        found[match[1]] = value
    return found


def load_env_files(paths):
    """Set each name the files give that the environment lacks; return the names set.

    NOTE: a real environment variable wins, an earlier file wins over a later one, and an empty
    value sets nothing, so a template such as ``.env.example`` changes nothing. No value is shown.
    """
    loaded = []
    for path in paths:
        if not path.is_file():
            continue
        for name, value in read_env_file(path).items():
            if value and name not in os.environ:
                os.environ[name] = value
                loaded.append(name)
    return loaded
