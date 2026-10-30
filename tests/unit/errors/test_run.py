"""Errors of running."""

import pytest

from geomind.errors import GeomindError, LoopError, ReplayError, RequestError, RunError, StateError


@pytest.mark.parametrize(
    ("error", "builtins"),
    [
        (RunError, (RuntimeError,)),
        (RequestError, (ValueError,)),
        (ReplayError, (RuntimeError,)),
        (LoopError, (RuntimeError,)),
    ],
)
def test_classes_derive_from_their_builtin(error, builtins):
    """Each class is caught by the matching built-in exception."""
    assert issubclass(error, builtins)


def test_state_error_is_a_value_error():
    """An invalid patch is a wrong value."""
    assert issubclass(StateError, ValueError) and issubclass(StateError, GeomindError)
