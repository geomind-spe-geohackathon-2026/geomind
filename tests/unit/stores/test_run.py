"""The memory store; the checks of ``gd.testing`` cover the protocol."""

import pytest

from geomind.errors import RunError
from geomind.stores.run import FileRunStore, MemoryRunStore
from geomind.types import Message
from geomind.types.events import StepStarted
from tests.fixtures.runs import call, run, says, uses


def test_missing_values_read_as_empty():
    """Unknown ids are not errors."""
    store = MemoryRunStore()
    assert store.load_history("x") == []
    assert store.load_state("x") is None
    assert store.load_artifact("x", "k") is None
    assert store.load_events("x") == []


def test_saved_values_are_copies():
    """Changing a value after saving changes nothing."""
    store = MemoryRunStore()
    value = {"a": [1]}
    store.save_state("r", value)
    value["a"].append(2)
    assert store.load_state("r") == {"a": [1]}


def test_history_keeps_its_order():
    """Messages stay oldest first."""
    store = MemoryRunStore()
    store.add_message("c", Message(role="user", content="1"))
    store.add_message("c", Message(role="assistant", content="2"))
    assert [message.content for message in store.load_history("c")] == ["1", "2"]


def test_file_store_layout(tmp_path):
    """Files land where the docs say."""
    store = FileRunStore(tmp_path)
    store.save_event("r", StepStarted(run_id="r", index=1))
    store.save_artifact("r", "k", b"x")
    store.add_message("c", Message(role="user", content="1"))
    store.save_state("c", {"s": 1})
    files = {path.relative_to(tmp_path).as_posix() for path in tmp_path.rglob("*.*")}
    assert files == {
        "r/events.jsonl",
        "r/artifacts/k.bin",
        "chats/c/history.jsonl",
        "chats/c/state.json",
    }


@pytest.mark.parametrize("name", ["../up", "a/b", "..", ""])
def test_file_store_refuses_unsafe_names(tmp_path, name):
    """An id or key never leaves the root folder."""
    store = FileRunStore(tmp_path)
    with pytest.raises(RunError, match="expected letters"):
        store.save_artifact("r", name, b"x")
    with pytest.raises(RunError, match="expected letters"):
        store.load_state(name)


@pytest.mark.parametrize("data", [b"x", {"a": 1}])
@pytest.mark.parametrize("key", ["design/doublet", "result/r1"])
def test_file_store_keeps_the_frozen_references(tmp_path, key, data):
    """The two reference formats of ``tools.md`` are keys."""
    store = FileRunStore(tmp_path)
    store.save_artifact("r", key, data)
    assert store.load_artifact("r", key) == data


@pytest.mark.parametrize("key", ["design/../up", "design/a/b", "result/", "design/.."])
def test_file_store_refuses_an_unsafe_reference(tmp_path, key):
    """A reference never leaves the run's folder."""
    with pytest.raises(RunError, match="expected letters"):
        FileRunStore(tmp_path).save_artifact("r", key, b"x")


async def test_large_tool_result_is_an_artifact_in_the_store(tmp_path):
    """A run saves a large result and the model reads a reference."""
    from geomind import runtime

    store = FileRunStore(tmp_path)
    with runtime.settings(tool_result_limit=30):
        result, _, events = await run([uses(call("lookup", key="k" * 100)), says()], store=store)
    recorded = [event for event in events if event.type == "tool.result"][0]
    assert recorded.reference == recorded.output["reference"]
    assert "k" * 100 in store.load_artifact(result.run_id, recorded.reference)
