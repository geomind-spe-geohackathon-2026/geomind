"""The tools the engine itself understands."""

import hashlib
from typing import Any

from geomind.tools.base import tool
from geomind.types import Finish, Option, Request
from geomind.types.decisions import typed_answer

QUESTION_CHARS = 300
"""How much of a question the answer's assumption keeps."""


@tool(effect="read", runs_alone=True)
async def ask_user(question: str, options: list[str | Option] | None = None):
    """Ask the user a question and wait for the answer, with fixed options if there are any.

    With ``options`` the user picks one option's value or types an answer of their own, which
    comes back marked as typed. To ask for something typed (a path, a number with its unit, a
    name), ask without options. Every answer is kept in the problem state as a confirmed user
    assumption (``answer.<id>``) that every later agent reads: read the state first and never ask
    a question it already answers; act on that answer instead.
    """
    return Request(kind="question", message=question, options=options)


def answer_change(problem, question, text):
    """Return the ``update_state`` operation that keeps the user's answer to ``question`` (QA-009).

    The id comes from the question, so the same question asked again replaces its answer.
    """
    key = "answer." + hashlib.sha1(question.encode()).hexdigest()[:8]
    asked = question if len(question) <= QUESTION_CHARS else question[:QUESTION_CHARS] + "..."
    assumption = {
        "id": key,
        "text": f"The user was asked: {asked} The user answered: {text}",
        "value": text,
        "source": "user",
        "confirmed": True,
        "reason": "the user's answer to ask_user; do not ask it again",
    }
    if key in {item.id for item in problem.assumptions}:
        return {"op": "replace", "path": f"/assumptions/{key}", "value": assumption}
    return {"op": "add", "path": "/assumptions/-", "value": assumption}


async def user_answered(context, tool_input, text):
    """Keep the user's answer in the problem state and return what the model reads of it."""
    question = str(tool_input.get("question") or "")
    request = Request(kind="question", message=question, options=tool_input.get("options"))
    if question and getattr(context, "problem", None) is not None:
        try:
            await context.session.change_state([answer_change(context.problem, question, text)])
        except ValueError:
            pass  # the answer still reaches the model; only its record in the state is missing
    return typed_answer(request, text)


ask_user.on_answer = user_answered


@tool(effect="read", runs_alone=True)
async def finish(answer: Any):
    """End the run with the final answer."""
    return Finish(answer=answer)
