"""The tools the engine understands."""

from geomind.tools import ask_user, finish
from geomind.types import Finish, Request


async def test_ask_user_is_a_question():
    """It returns a request of kind ``question``."""
    request = await ask_user.function(None, question="which?")
    assert request == Request(kind="question", message="which?")


async def test_ask_user_normalises_options():
    """Strings and ``{value, label}`` are both accepted through the tool's own validation."""
    arguments = ask_user.validate(
        {"question": "q", "options": ["water", {"value": "brine", "label": "Salt water"}]}
    )
    request = await ask_user.function(None, **arguments)
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


def test_ask_user_says_a_typed_answer_needs_no_options():
    """#59: the case lead asked for a path and a value with options, and the user could not."""
    from geomind.tools import ask_user

    from geomind.context.skills import load_skill

    assert "working-in-a-team" in ask_user.schema()["description"]
    text = " ".join(load_skill("working-in-a-team").split())
    assert "types an answer of their own" in text and "ask without options" in text


async def test_a_question_that_retypes_a_long_number_is_refused_with_its_source():
    """QA-163: the question showed 0.110838972435462335; the source writes 0.11083897243546233."""
    from types import SimpleNamespace

    import pytest

    from geomind.errors import ToolError
    from geomind.types import Message

    source = Message(role="tool", tool_call_id="c1", content='{"N2": 0.11083897243546233}')
    context = SimpleNamespace(messages=[source], problem=None)
    with pytest.raises(ToolError, match="0.11083897243546233"):
        await ask_user.function(context, question="N2 0.110838972435462335, right?")
    right = await ask_user.function(context, question="N2 0.11083897243546233 and 0.5, right?")
    assert right.kind == "question"
