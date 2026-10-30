"""What hooks, permissions and tools decide, and the answers to a request."""

from typing import Any, Literal

from swarmax.core.types.messages import Record
from swarmax.errors import RequestError


class Request(Record):
    """A pause for the user; the engine fills in ``id`` when it pauses the run."""

    kind: Literal["approval", "question"]
    message: str
    id: str = ""
    options: tuple[str, ...] | None = None
    call_id: str | None = None


class Allow(Record):
    """No objection; ``input`` optionally replaces the tool input."""

    input: dict[str, Any] | None = None


class Deny(Record):
    """A refusal with the reason given to the model or the log."""

    reason: str


class Cancel(Deny):
    """A refusal that ends the run with ``stop_reason="cancelled"`` at any hook point."""


class Finish(Record):
    """What the ``finish`` tool returns: the proposed final answer."""

    answer: Any


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
    """Check that ``answer`` has the contract shape for ``request``; return it."""
    if not isinstance(answer, dict):
        raise RequestError(f"answer = {answer!r}; expected a dictionary")
    if request.kind == "approval":
        _check_approval(answer)
        return answer
    if set(answer) != {"text"} or not isinstance(answer["text"], str):
        raise RequestError(f"answer = {answer!r}; expected {{'text': '...'}}")
    return answer
