"""Errors of running."""

import pytest

from swarmax.errors import CheckpointError, LoopError, ReplayError, RequestError, RunError


@pytest.mark.parametrize(
    ("error", "builtins"),
    [
        (RunError, (RuntimeError,)),
        (RequestError, (ValueError,)),
        (CheckpointError, (RuntimeError, ValueError)),
        (ReplayError, (RuntimeError,)),
        (LoopError, (RuntimeError,)),
    ],
)
def test_classes_derive_from_their_builtin(error, builtins):
    """Each class is caught by the matching built-in exception."""
    assert issubclass(error, builtins)
