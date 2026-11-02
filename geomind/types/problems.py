"""The shape of a tool's error result: gemini's Problem."""

from geomind.types.messages import Record

TOOL_ERROR_CODES = (
    "invalid_input",
    "unknown_name",
    "not_implemented",
    "not_allowed",
    "timeout",
    "budget",
    "internal",
)
"""The codes of geomind's own errors; a gemini error keeps its code from ``gm.errors.CODES``."""


class Problem(Record):
    """What went wrong: ``path`` is the input field at fault, ``code`` the stable key."""

    path: str | None = None
    code: str
    message: str
    suggestions: tuple[str, ...] = ()


class ToolErrorOutput(Record):
    """The output of a tool call that failed."""

    error: Problem
