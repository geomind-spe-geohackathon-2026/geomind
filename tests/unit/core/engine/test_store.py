"""The memory store; the checks of ``sx.testing`` cover the protocol."""

from swarmax.core.engine.store import MemoryRunStore
from swarmax.core.types import Message


def test_missing_values_read_as_empty():
    """Unknown ids are not errors."""
    store = MemoryRunStore()
    assert store.load_checkpoint("x") is None
    assert store.load_history("x") == []
    assert store.load_state("x") is None
    assert store.load_artifact("x", "k") is None
    assert store.load_events("x") == []


def test_saved_values_are_copies():
    """Changing a value after saving changes nothing."""
    store = MemoryRunStore()
    value = {"a": [1]}
    store.save_checkpoint("r", value)
    value["a"].append(2)
    assert store.load_checkpoint("r") == {"a": [1]}


def test_history_keeps_its_order():
    """Messages stay oldest first."""
    store = MemoryRunStore()
    store.add_message("c", Message(role="user", content="1"))
    store.add_message("c", Message(role="assistant", content="2"))
    assert [message.content for message in store.load_history("c")] == ["1", "2"]
