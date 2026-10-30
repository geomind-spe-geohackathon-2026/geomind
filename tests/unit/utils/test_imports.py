"""Classes named by strings."""

import pytest

from geomind.utils.imports import class_path, import_class
from tests.fixtures.runs import Worker


def test_class_path_round_trip():
    """A stored class path imports the class."""
    assert import_class(class_path(Worker)) is Worker


@pytest.mark.parametrize("path", ["no.such.module:X", "tests.fixtures.runs:Nothing", "bad"])
def test_bad_class_path_raises(path):
    """A path that imports nothing says so."""
    with pytest.raises(ImportError, match="importable"):
        import_class(path)
