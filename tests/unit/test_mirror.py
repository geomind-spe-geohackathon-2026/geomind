"""Every source file has a mirrored unit test file that defines a test."""

import ast

import pytest

from tests.fixtures import ROOT

PACKAGE = ROOT / "swarmax"
SOURCES = sorted(
    path for path in PACKAGE.rglob("*.py") if path.name not in {"__init__.py", "__main__.py"}
)


def mirror(path):
    """Return the mirrored test path of one source file."""
    relative = path.relative_to(PACKAGE)
    return ROOT / "tests/unit" / relative.parent / f"test_{relative.name}"


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(PACKAGE)))
def test_source_has_a_mirrored_test(path):
    """The mirror exists and defines at least one test."""
    tests = mirror(path)
    assert tests.exists(), f"missing {tests.relative_to(ROOT)}"
    names = [
        node.name
        for node in ast.walk(ast.parse(tests.read_text()))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    ]
    assert any(name.startswith("test_") for name in names)
