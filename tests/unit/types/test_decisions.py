"""Decisions and the shape of answers."""

import pydantic
import pytest

from geomind.errors import RequestError
from geomind.types import Cancel, Deny, Option, Request, validate_answer

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


def test_plain_strings_become_options():
    """Strings and ``{value, label}`` meet in one shape, and no choices means free text."""
    mixed = Request(kind="question", message="m", options=["a", {"value": "b", "label": "B"}])
    assert mixed.options == (Option(value="a", label="a"), Option(value="b", label="B"))
    assert Request(kind="question", message="m", options=[]).options is None


def test_approvals_have_no_options():
    """The contract leaves them out."""
    with pytest.raises(pydantic.ValidationError, match="only on a question"):
        Request(kind="approval", message="m", options=["a"])


def test_an_answer_that_is_no_option_is_typed_text():
    """The run: the user's values to [approve all, change some, stop] were refused; now typed."""
    from geomind.types.decisions import is_typed, typed_answer

    options = ["approve all", "change some", "stop"]
    request = Request(kind="question", message="m", options=options)
    text = (
        "demand.heating.return_temperature and demand.cooling.return_temperature: the "
        "designers' choice. Everything else in this list: unknown."
    )
    assert validate_answer(request, {"text": text}) == {"text": text}
    assert is_typed(request, text) and not is_typed(request, "change some")
    assert typed_answer(request, "change some") == "change some"
    assert typed_answer(request, text).endswith(text) and "typed" in typed_answer(request, text)
    assert not is_typed(Request(kind="question", message="m"), text)


def test_cancel_is_a_deny():
    """A cancellation is a refusal the engine treats as its own stop reason."""
    assert isinstance(Cancel(reason="stop"), Deny)
