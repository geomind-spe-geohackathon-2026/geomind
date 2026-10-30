"""The tools the engine itself understands."""

from typing import Any

from swarmax.core.types import Finish, Request
from swarmax.tools.base import tool


@tool(effect="read", runs_alone=True)
async def ask_user(question: str, options: list[str] | None = None):
    """Ask the user a question and wait for the answer."""
    return Request(kind="question", message=question, options=tuple(options) if options else None)


@tool(effect="read", runs_alone=True)
async def finish(answer: Any):
    """End the run with the final answer."""
    return Finish(answer=answer)
