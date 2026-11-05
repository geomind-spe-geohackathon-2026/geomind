"""The tools the engine itself understands."""

import hashlib
import json
import re
from typing import Any

from geomind.context.skills import tool_section
from geomind.errors import ToolError
from geomind.tools.base import tool
from geomind.types import Finish, Option, Request
from geomind.types.decisions import typed_answer

QUESTION_CHARS = 300
"""How much of a question the answer's assumption keeps."""


LONG_DIGITS = 8
"""Significant digits from which a number of a question is checked against its source (QA-163)."""
SAME_LEAD = 6
"""Leading digits two numbers share when one is a retyping of the other."""
NUMBER = re.compile(r"(?<![\w.])-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def digits_of(number):
    """Return the significant digits of a number as written: ``0.0123`` gives ``123``."""
    mantissa = re.split(r"[eE]", number.lstrip("-"))[0]
    return mantissa.replace(".", "").lstrip("0")


def source_numbers(context):
    """Return every number the run's sources hold, as written: tool results, the user's words,
    the inputs of calls other than ``ask_user`` and the case. The model's own text is no source.
    """
    found = set()
    for message in getattr(context, "messages", None) or ():
        text = message.content if isinstance(message.content, str) else ""
        if message.role != "assistant":
            found.update(NUMBER.findall(text))
        for call in getattr(message, "tool_calls", None) or ():
            if call.name != "ask_user":
                found.update(NUMBER.findall(json.dumps(call.input, default=str)))
    case = getattr(getattr(context, "problem", None), "case", None)
    if case:
        found.update(NUMBER.findall(json.dumps(case, default=str)))
    return found


def retyped_numbers(context, question):
    """Return ``[(written, source)]``: long numbers of ``question`` that differ from their source.

    QA-163: the confirmation question showed N2 ``0.110838972435462335`` where the source and the
    case hold ``0.11083897243546233``; the user approves what the question shows. A long number
    the run's messages do not hold, but one with the same first digits, is a retyping.
    """
    if context is None:
        return []
    known = source_numbers(context)
    wrong = []
    for written in dict.fromkeys(NUMBER.findall(question)):
        digits = digits_of(written)
        if len(digits) < LONG_DIGITS or written in known:
            continue
        near = [
            number
            for number in known
            if digits_of(number)[:SAME_LEAD] == digits[:SAME_LEAD]
            and len(digits_of(number)) >= LONG_DIGITS
            and digits_of(number) != digits
        ]
        if near:
            wrong.append((written, sorted(near)[0]))
    return wrong


@tool(effect="read", runs_alone=True)
async def ask_user(context, question: str, options: list[str | Option] | None = None):
    """Ask the user a question and wait for the answer, with fixed options if there are any.

    Skill `working-in-a-team`.
    """
    wrong = retyped_numbers(context, question)
    if wrong:
        shown = "; ".join(
            f"{written} where the source writes {source}" for written, source in wrong
        )
        raise ToolError(
            f"ask_user: the question retypes {len(wrong)} number(s) with other digits: {shown}. "
            "Copy each number digit for digit from its source (or the case), and ask again",
            code="invalid_value",
            path="question",
            suggestions=[f"{written} -> {source}" for written, source in wrong],
        )
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
ask_user.description = f"{ask_user.description}\n\n{tool_section('ask_user')}"


@tool(effect="read", runs_alone=True)
async def finish(answer: Any):
    """End the run with the final answer. Skill `working-in-a-team`."""
    return Finish(answer=answer)
