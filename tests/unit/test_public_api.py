"""The curated user API, pinned name by name."""

import tomllib

import pytest

import swarmax as sx
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
    "agents",
    "tools",
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
BUILT = {
    "providers",
    "Message",
    "Action",
    "Request",
    "Allow",
    "Deny",
    "RunResult",
    "runlog",
    "runtime",
    "errors",
    "__version__",
}
NOT_BUILT = set(EXPECTED) - BUILT


@pytest.mark.parametrize(
    "name",
    [
        (
            pytest.param(name, marks=pytest.mark.xfail(strict=True, reason="not built yet"))
            if name in NOT_BUILT
            else name
        )
        for name in EXPECTED
    ],
)
def test_public_name_exists_and_is_listed(name):
    """Every curated name exists, is exported and shows in completion."""
    assert hasattr(sx, name) and name in sx.__all__ and name in dir(sx)


def test_nothing_else_is_public():
    """Interactive completion shows only the curated names."""
    assert set(dir(sx)) == set(sx.__all__) <= set(EXPECTED)


def test_version_matches_the_package_metadata():
    """The version literal in ``swarmax/__init__.py`` is the one in ``pyproject.toml``."""
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    assert sx.__version__ == project["project"]["version"]
