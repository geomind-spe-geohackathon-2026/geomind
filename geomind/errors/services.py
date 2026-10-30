"""Errors of what the harness calls: LLM services, tools and sandboxes."""

from geomind.errors.base import GeomindError


class ProviderError(GeomindError, RuntimeError):
    """An LLM call failed; ``status`` is the HTTP status, ``is_retryable`` says to try again."""

    def __init__(self, message, *, status=None, is_retryable=False):
        """Store the message, the HTTP status if there was one, and whether a retry can help."""
        super().__init__(message)
        self.status = status
        self.is_retryable = is_retryable


class ToolError(GeomindError, RuntimeError):
    """A tool failed deliberately, timed out or was interrupted by a crash."""


class SandboxError(GeomindError, RuntimeError):
    """A sandbox is missing, lost or was asked for a path outside itself."""
