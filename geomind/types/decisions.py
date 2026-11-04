"""What hooks, permissions and tools decide, and the answers to a request."""

from typing import Any, Literal

from pydantic import field_validator, model_validator

from geomind.errors import RequestError
from geomind.types.messages import Record


class Option(Record):
    """One fixed choice of a question: ``value`` is the answer, ``label`` what the user reads."""

    value: str
    label: str


class Request(Record):
    """A pause for the user; the engine fills in ``id`` when it pauses the run.

    ``options`` are the fixed choices of a question. Plain strings become options with the same
    value and label, which is also how a run stored by S1 holds them.
    """

    kind: Literal["approval", "question"]
    message: str
    id: str = ""
    options: tuple[Option, ...] | None = None
    call_id: str | None = None

    @field_validator("options", mode="before")
    @classmethod
    def _normalise_options(cls, options):
        """Turn plain strings into options; no choices means free text."""
        if not options:
            return None
        return [dict(value=o, label=o) if isinstance(o, str) else o for o in options]

    @model_validator(mode="after")
    def _only_questions_have_options(self):
        """Refuse fixed choices on an approval, which is answered yes or no."""
        if self.kind == "approval" and self.options:
            raise ValueError("options = fixed choices; expected them only on a question")
        return self


class Approval(Record):
    """The answer to an approval: ``approved``, with a ``reason`` on a refusal."""

    approved: bool
    reason: str | None = None


class Reply(Record):
    """The answer to a question: free text, or the value of one option.

    A question with options takes typed text too: text that is no option's value is the user's
    own answer, which the model reads as typed (``typed_answer``).
    """

    text: str


Answer = Approval | Reply
"""The shapes of an answer; ``validate_answer`` checks one against its request."""


class Allow(Record):
    """No objection; ``input`` optionally replaces the tool input."""

    input: dict[str, Any] | None = None


class Deny(Record):
    """A refusal with the reason given to the model or the log."""

    reason: str


class Cancel(Deny):
    """A refusal that ends the run with ``stop_reason="cancelled"`` at any hook point."""


class Finish(Record):
    """What the ``finish`` tool returns: the proposed final answer.

    ``suggestions`` are the next steps the project lead proposes, checked by code
    (``geomind.tools.suggestions``).
    """

    answer: Any
    suggestions: list[dict[str, Any]] | None = None


def _check_approval(answer):
    """Reject anything but ``{"approved": bool}`` with an optional ``reason``."""
    has_reason = "reason" in answer and isinstance(answer["reason"], str)
    is_valid = isinstance(answer.get("approved"), bool) and set(answer) <= {"approved", "reason"}
    if not is_valid or ("reason" in answer and not has_reason):
        raise RequestError(
            f"answer = {answer!r}; expected {{'approved': true}} or "
            "{'approved': false, 'reason': '...'}"
        )


def validate_answer(request, answer):
    """Check that ``answer`` has the contract shape for ``request``; return it.

    The text of a question with options may be any text: an option's value, or the user's own
    words when no option fits (a value, a correction).
    """
    if not isinstance(answer, dict):
        raise RequestError(f"answer = {answer!r}; expected a dictionary")
    if request.kind == "approval":
        _check_approval(answer)
        return answer
    if set(answer) != {"text"} or not isinstance(answer["text"], str):
        raise RequestError(f"answer = {answer!r}; expected {{'text': '...'}}")
    return answer


def is_typed(request, text):
    """Tell whether ``text`` answers a question with options by none of them."""
    values = [option.value for option in request.options or ()]
    return bool(values) and text not in values


def typed_answer(request, text):
    """Return what the model reads of a reply: an option's value as is, typed text marked so."""
    if not is_typed(request, text):
        return text
    return f"The user typed this answer instead of choosing an option: {text}"
