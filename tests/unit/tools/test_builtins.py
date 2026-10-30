"""The tools the engine understands."""

from swarmax.tools import ask_user, finish
from swarmax.types import Finish, Request


async def test_ask_user_is_a_question():
    """It returns a request of kind ``question``."""
    request = await ask_user.function(question="which?")
    assert request == Request(kind="question", message="which?")


async def test_finish_carries_the_answer():
    """It returns the proposed answer."""
    assert await finish.function(answer={"a": 1}) == Finish(answer={"a": 1})


def test_neither_needs_a_sandbox_or_approval():
    """Both are read tools, so ``ask`` mode lets them through."""
    assert ask_user.effect == "read" and finish.effect == "read"
