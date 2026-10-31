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
    """A tool failed deliberately, timed out or was interrupted by a crash.

    ``code`` is one of the error codes of ``tools.md`` and ``path`` the input field at fault.
    """

    def __init__(self, message, *, code="invalid_input", path=None):
        """Store the message with what the result of the tool says about it."""
        super().__init__(message)
        self.code = code
        self.path = path


class SandboxError(GeomindError, RuntimeError):
    """A sandbox is missing, lost or was asked for a path outside itself."""


class NotImplementedYet(GeomindError, NotImplementedError):
    """A capability has its final signature and is not built yet; the message names its phase."""
