"""The tools the engine itself understands."""

from typing import Any

from geomind.tools.base import tool
from geomind.types import Finish, Option, Request


@tool(effect="read", runs_alone=True)
async def ask_user(question: str, options: list[str | Option] | None = None):
    """Ask the user a question and wait for the answer, with fixed options if there are any.

    With ``options`` the answer is exactly one option's value: the user cannot type anything
    else. To get something typed (a path, a number with its unit, a name), ask without options.
    """
    return Request(kind="question", message=question, options=options)


@tool(effect="read", runs_alone=True)
async def finish(answer: Any):
    """End the run with the final answer."""
    return Finish(answer=answer)
