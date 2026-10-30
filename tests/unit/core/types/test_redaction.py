"""Known secrets never reach a store or a stream."""

from swarmax.core.types import Completion, Message
from swarmax.core.types.events import LLMCompleted
from swarmax.core.types.redaction import REDACTED, redact, redact_event


def test_redact_walks_nested_values():
    """Strings at any depth lose the secret, other values stay."""
    value = {"a": ["key sk-1 end", 3], "b": ("sk-1",)}
    assert redact(value, ("sk-1",)) == {"a": [f"key {REDACTED} end", 3], "b": [REDACTED]}


def test_redact_event_cleans_the_full_completion():
    """Messages and completion text are both cleaned, and the event stays typed."""
    event = LLMCompleted(
        run_id="r",
        index=1,
        completion=Completion(text="sk-1"),
        messages=(Message(role="user", content="use sk-1"),),
    )
    clean = redact_event(event, ("sk-1",))
    assert isinstance(clean, LLMCompleted) and "sk-1" not in clean.model_dump_json()


def test_no_secrets_returns_the_same_event():
    """The common case costs nothing."""
    event = LLMCompleted(run_id="r", index=1, completion=Completion())
    assert redact_event(event, ()) is event


def test_redact_cleans_bytes():
    """A binary artifact loses the secret too."""
    assert redact(b"a sk-1 b", ("sk-1",)) == f"a {REDACTED} b".encode()
