"""The development profile selects what changed and everything importing it."""

from scripts.test_changed import mirror_test, select_tests


def graph():
    """Return a small import graph: a test and a module importing ``swarmax.leaf``."""
    return {
        "swarmax/leaf.py": set(),
        "swarmax/user.py": {"swarmax", "swarmax.leaf"},
        "tests/unit/test_leaf.py": {"swarmax.leaf"},
        "tests/unit/test_user.py": {"swarmax.user"},
        "tests/unit/test_other.py": set(),
    }


def test_changed_module_selects_its_importers(tmp_path):
    """Importers are followed transitively through their mirrors and test files."""
    selected = select_tests(["swarmax/leaf.py"], graph(), tmp_path)
    assert set(selected) == {"tests/unit/test_leaf.py", "tests/unit/test_user.py"}


def test_pyproject_selects_everything(tmp_path):
    """Configuration changes run every test."""
    selected = select_tests(["pyproject.toml"], graph(), tmp_path)
    assert len(selected) == 3


def test_mirror_test_skips_package_files():
    """A package file has no mirror."""
    assert mirror_test("swarmax/core/runtime.py") == "tests/unit/core/test_runtime.py"
    assert mirror_test("swarmax/core/__init__.py") is None
