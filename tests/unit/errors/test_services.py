"""Errors of what the harness calls."""

from geomind.errors import (
    GeomindError,
    NotImplementedYet,
    ProviderError,
    SandboxError,
    ToolError,
)


def test_provider_error_carries_status_and_retry_advice():
    """The retry layer reads these fields."""
    error = ProviderError("busy", status=429, is_retryable=True)
    assert (error.status, error.is_retryable, str(error)) == (429, True, "busy")
    assert ProviderError("bad").is_retryable is False


def test_classes_derive_from_their_builtin():
    """Each class is caught by ``RuntimeError``."""
    assert issubclass(ToolError, RuntimeError) and issubclass(SandboxError, RuntimeError)


def test_not_implemented_yet_is_both_kinds():
    """Catching ``GeomindError`` or the built-in both work."""
    error = NotImplementedYet("simulate comes in S2b")
    assert isinstance(error, GeomindError) and isinstance(error, NotImplementedError)


def test_a_tool_error_defaults_to_invalid_input():
    """Without a code, the call was wrong."""
    error = ToolError("no")
    assert (error.code, error.path) == ("invalid_input", None)
