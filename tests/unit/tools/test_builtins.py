"""The tools the engine understands."""

from geomind.tools import ask_user, finish
from geomind.types import Finish, Request


async def test_ask_user_is_a_question():
    """It returns a request of kind ``question``."""
    request = await ask_user.function(question="which?")
    assert request == Request(kind="question", message="which?")


async def test_ask_user_normalises_options():
    """Strings and ``{value, label}`` are both accepted through the tool's own validation."""
    arguments = ask_user.validate(
        {"question": "q", "options": ["water", {"value": "brine", "label": "Salt water"}]}
    )
    request = await ask_user.function(**arguments)
    assert [option.model_dump() for option in request.options] == [
        {"value": "water", "label": "water"},
        {"value": "brine", "label": "Salt water"},
    ]


async def test_finish_carries_the_answer():
    """It returns the proposed answer."""
    assert await finish.function(answer={"a": 1}) == Finish(answer={"a": 1})


def test_neither_needs_a_sandbox_or_approval():
    """Both are read tools, so ``ask`` mode lets them through."""
    assert ask_user.effect == "read" and finish.effect == "read"
