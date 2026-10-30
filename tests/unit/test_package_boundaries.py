"""Each package imports only the packages to its left, in the order of ``conventions.md``."""

import ast

import pytest

from tests.fixtures import ROOT

ORDER = [
    ("swarmax.utils",),
    ("swarmax.errors",),
    ("swarmax.core.types",),
    ("swarmax.core.runtime",),
    ("swarmax.core.prompts",),
    ("swarmax.providers",),
    ("swarmax.sandbox",),
    ("swarmax.tools",),
    ("swarmax.core.agents",),
    ("swarmax.core.engine",),
    ("swarmax.stores",),
    ("swarmax.loops",),
    ("swarmax.run",),
    ("swarmax.testing",),
    ("swarmax.cli",),
]
LEAVES = {"swarmax.utils", "swarmax.errors"}
SOURCES = sorted((ROOT / "swarmax").rglob("*.py"))


def module_name(path):
    """Return the dotted name of one source file."""
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imported_modules(path):
    """Return the dotted ``swarmax`` modules one file imports, with imported submodules."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path}: use absolute imports"
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return {name for name in names if name.startswith("swarmax.")}


def rank(name):
    """Return the position of the package owning a dotted name, or ``None`` for the top level."""
    for index, (package,) in enumerate(ORDER):
        if name == package or name.startswith(f"{package}."):
            return index
    return None


@pytest.mark.parametrize("path", SOURCES, ids=lambda path: str(path.relative_to(ROOT)))
def test_imports_follow_the_dependency_order(path):
    """A package imports itself and packages to its left; leaves import only themselves."""
    own = rank(module_name(path))
    if own is None:
        return
    allowed_to_left = ORDER[own][0] not in LEAVES
    bad = []
    for name in sorted(imported_modules(path)):
        other = rank(name)
        if other is None or other > own or (other != own and not allowed_to_left):
            bad.append(name)
    assert bad == []


def test_rank_finds_the_owner_package():
    """A submodule belongs to its package and the package root to nothing."""
    assert rank("swarmax.core.engine.step") > rank("swarmax.tools.base")
    assert rank("swarmax") is None
