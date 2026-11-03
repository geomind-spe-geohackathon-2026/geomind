"""Refuse a release tag that differs from the version of the package.

Usage::

    python scripts/check_release.py v0.4.3
"""

import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def versions():
    """Return the versions of ``pyproject.toml`` and ``geomind/__init__.py``."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    package = re.search(r'^__version__ = "(.+)"$', (ROOT / "geomind/__init__.py").read_text(), re.M)
    return project["version"], package.group(1)


def main(tag):
    """Exit with a message unless ``tag`` is ``v`` and the version both files name."""
    project, package = versions()
    if tag != f"v{project}" or project != package:
        sys.exit(f"tag {tag}, pyproject {project}, geomind {package}: they must agree")


if __name__ == "__main__":
    main(sys.argv[1])
