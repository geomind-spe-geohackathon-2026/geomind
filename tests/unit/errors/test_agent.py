"""Errors of defining agents."""

import pytest

from swarmax.errors import DeclarationError, OutputError, UnknownNameError


@pytest.mark.parametrize(
    ("error", "builtins"),
    [
        (DeclarationError, (TypeError, ValueError)),
        (UnknownNameError, (ValueError,)),
        (OutputError, (ValueError,)),
    ],
)
def test_classes_derive_from_their_builtin(error, builtins):
    """Each class is caught by the matching built-in exception."""
    assert issubclass(error, builtins)
