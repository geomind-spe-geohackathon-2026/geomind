"""The curated user API, pinned name by name."""

import tomllib

import pytest

import geomind as gd
from tests.fixtures import ROOT

EXPECTED = (
    "Run",
    "Agent",
    "Engine",
    "Tool",
    "tool",
    "Prompt",
    "Model",
    "Output",
    "Context",
    "Message",
    "Action",
    "Request",
    "Allow",
    "Deny",
    "Permissions",
    "RunResult",
    "runlog",
    "event_from_dict",
    "agents",
    "tools",
    "verify",
    "loops",
    "hooks",
    "callbacks",
    "providers",
    "sandbox",
    "stores",
    "testing",
    "runtime",
    "errors",
    "__version__",
)


@pytest.mark.parametrize("name", EXPECTED)
def test_public_name_exists_and_is_listed(name):
    """Every curated name exists, is exported and shows in completion."""
    assert hasattr(gd, name) and name in gd.__all__ and name in dir(gd)


def test_nothing_else_is_public():
    """Interactive completion shows only the curated names."""
    assert set(dir(gd)) == set(gd.__all__) == set(EXPECTED)


def test_stores_namespace():
    """The four implementations are public."""
    names = ("MemoryRunStore", "FileRunStore", "MemoryWorkspace", "FileWorkspace")
    assert all(hasattr(gd.stores, name) for name in names)


def test_version_matches_the_package_metadata():
    """The version literal in ``geomind/__init__.py`` is the one in ``pyproject.toml``."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert gd.__version__ == project["project"]["version"]
