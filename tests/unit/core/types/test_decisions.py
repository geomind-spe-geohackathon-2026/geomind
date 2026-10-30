"""Decisions and the shape of answers."""

import pytest

from swarmax.core.types import Cancel, Deny, Request, validate_answer
from swarmax.errors import RequestError

APPROVAL = Request(kind="approval", message="ok?")
QUESTION = Request(kind="question", message="which?")


@pytest.mark.parametrize("answer", [{"approved": True}, {"approved": False, "reason": "no"}])
def test_approval_answers(answer):
    """The contract shapes of an approval pass unchanged."""
    assert validate_answer(APPROVAL, answer) == answer


def test_question_answer():
    """A question takes text."""
    assert validate_answer(QUESTION, {"text": "this"}) == {"text": "this"}


@pytest.mark.parametrize(
    ("request_", "answer"),
    [
        (APPROVAL, {"text": "x"}),
        (APPROVAL, {"approved": "yes"}),
        (APPROVAL, {"approved": False, "reason": 1}),
        (APPROVAL, {"approved": True, "extra": 1}),
        (QUESTION, {"approved": True}),
        (QUESTION, {"text": 1}),
        (QUESTION, "text"),
    ],
)
def test_wrong_shapes_raise(request_, answer):
    """Anything else raises ``RequestError``."""
    with pytest.raises(RequestError):
        validate_answer(request_, answer)


def test_cancel_is_a_deny():
    """A cancellation is a refusal the engine treats as its own stop reason."""
    assert isinstance(Cancel(reason="stop"), Deny)
