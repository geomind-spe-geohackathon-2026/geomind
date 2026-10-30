"""Each package imports only the packages to its left, in the order of ``conventions.md``."""

import ast
import re

import pytest

from tests.fixtures import ROOT

ORDER = [
    ("geomind.utils",),
    ("geomind.errors",),
    ("geomind.types",),
    ("geomind.stores",),
    ("geomind.runtime",),
    ("geomind.prompts",),
    ("geomind.context",),
    ("geomind.providers",),
    ("geomind.sandbox",),
    ("geomind.tools",),
    ("geomind.agents",),
    ("geomind.engine",),
    ("geomind.loops",),
    ("geomind.run",),
    ("geomind.testing",),
    ("geomind.cli",),
]
CORE_IMPORT = re.compile(r"^\s*(?:from|import) +\S*\bcore\b.*$", re.MULTILINE)
LEAVES = {"geomind.utils", "geomind.errors"}
SOURCES = sorted((ROOT / "geomind").rglob("*.py"))


def module_name(path):
    """Return the dotted name of one source file."""
    parts = path.relative_to(ROOT).with_suffix("").parts
    return ".".join(parts[:-1] if parts[-1] == "__init__" else parts)


def imported_modules(path):
    """Return the dotted ``geomind`` modules one file imports, with imported submodules."""
    names = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        if isinstance(node, ast.ImportFrom):
            assert node.level == 0, f"{path}: use absolute imports"
            names.update(f"{node.module}.{alias.name}" for alias in node.names)
    return {name for name in names if name.startswith("geomind.")}


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
    assert rank("geomind.engine.step") > rank("geomind.tools.base")
    assert rank("geomind") is None


def test_stores_left_the_engine():
    """The store and workspace live only in their package."""
    assert not (ROOT / "geomind/engine/store.py").exists()
    assert not (ROOT / "geomind/engine/workspace.py").exists()
    assert not (ROOT / "geomind/stores.py").exists()


def all_python_files():
    """Return every Python file of the repository's own folders."""
    folders = ("geomind", "examples", "tests", "scripts")
    return [path for folder in folders for path in sorted((ROOT / folder).rglob("*.py"))]


def test_no_core_package_or_import_reappears():
    """The packages live at the top level, and no import goes through a ``core`` package."""
    assert not (ROOT / "geomind/core").exists() and not (ROOT / "tests/unit/core").exists()
    found = []
    for path in all_python_files():
        found += [f"{path}: {line}" for line in CORE_IMPORT.findall(path.read_text())]
    assert found == []
