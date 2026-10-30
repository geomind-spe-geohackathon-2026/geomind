"""Errors of what the harness calls."""

from geomind.errors import ProviderError, SandboxError, ToolError


def test_provider_error_carries_status_and_retry_advice():
    """The retry layer reads these fields."""
    error = ProviderError("busy", status=429, is_retryable=True)
    assert (error.status, error.is_retryable, str(error)) == (429, True, "busy")
    assert ProviderError("bad").is_retryable is False


def test_classes_derive_from_their_builtin():
    """Each class is caught by ``RuntimeError``."""
    assert issubclass(ToolError, RuntimeError) and issubclass(SandboxError, RuntimeError)
