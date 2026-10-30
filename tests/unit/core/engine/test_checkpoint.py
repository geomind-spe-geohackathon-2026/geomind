"""The checkpoint format."""

import pytest

from swarmax.core.engine.checkpoint import Checkpoint, class_path, import_class
from swarmax.errors import CheckpointError, RunError
from tests.fixtures.runs import Worker


def test_round_trip():
    """The JSON form rebuilds the checkpoint."""
    checkpoint = Checkpoint(run_id="r", step=2)
    assert Checkpoint.load(checkpoint.dump()) == checkpoint


@pytest.mark.parametrize("data", [{}, {"version": 2}, None, "text"])
def test_wrong_version_raises(data):
    """Another version is refused."""
    with pytest.raises(CheckpointError, match="version"):
        Checkpoint.load(data)


def test_wrong_shape_raises():
    """Unknown fields are refused."""
    with pytest.raises(CheckpointError, match="shape"):
        Checkpoint.load({"version": 1, "unknown": 1})


def test_class_path_round_trip():
    """A stored class path imports the class."""
    assert import_class(class_path(Worker)) is Worker


@pytest.mark.parametrize("path", ["no.such.module:X", "tests.fixtures.runs:Nothing", "bad"])
def test_bad_class_path_raises(path):
    """A path that imports nothing is a run error."""
    with pytest.raises(RunError, match="importable"):
        import_class(path)
