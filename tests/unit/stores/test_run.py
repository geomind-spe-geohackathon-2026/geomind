"""The memory store; the checks of ``gd.testing`` cover the protocol."""

import pytest

from geomind.errors import RunError
from geomind.stores.run import FileRunStore, MemoryRunStore
from geomind.types import Message
from geomind.types.events import StepStarted
from geomind.utils.json import append_line
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
@pytest.mark.parametrize("key", ["design/doublet", "result/r1", "module/heat_store.py"])
def test_file_store_keeps_the_frozen_references(tmp_path, key, data):
    """The two reference formats of ``tools.md`` are keys."""
    store = FileRunStore(tmp_path)
    store.save_artifact("r", key, data)
    assert store.load_artifact("r", key) == data


@pytest.mark.parametrize(
    "key", ["design/../up", "design/a/b", "result/", "design/..", "profile/demand"]
)
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
    assert "k" * 100 in store.load_chat_artifact(result.run_id, recorded.reference)


def test_file_store_keeps_a_case_file_under_its_name(tmp_path):
    """A file of the run's case is ``case/<file name>``, bytes as written."""
    store = FileRunStore(tmp_path)
    store.save_artifact("r", "case/demand.csv", b"time,x\n")
    assert (tmp_path / "r/artifacts/case/demand.csv.bin").read_bytes() == b"time,x\n"
    assert store.load_artifact("r", "case/demand.csv") == b"time,x\n"
    with pytest.raises(RunError, match="expected letters"):
        store.save_artifact("r", "case/../x", b"x")


def test_a_chat_has_its_own_artifact_space(tmp_path):
    """A chat's artifacts are not a run's, and a chat reads only its own."""
    for store in (MemoryRunStore(), FileRunStore(tmp_path)):
        store.save_chat_artifact("c", "case/data/demand.csv", b"x")
        store.save_chat_artifact("c", "design/d", {"a": 1})
        assert store.load_chat_artifact("c", "case/data/demand.csv") == b"x"
        assert store.load_chat_artifact("c", "design/d") == {"a": 1}
        assert store.load_chat_artifact("other", "design/d") is None
        assert store.load_artifact("c", "design/d") is None


def test_file_store_layout_of_a_chat_artifact(tmp_path):
    """The chat's artifacts are below the chat's folder, with the run keys' safe rules."""
    store = FileRunStore(tmp_path)
    store.save_chat_artifact("c", "design/d", {"a": 1})
    assert (tmp_path / "chats/c/artifacts/design/d.json").is_file()
    with pytest.raises(RunError, match="expected letters"):
        store.save_chat_artifact("c", "case/../x", b"x")


def test_the_file_store_skips_an_event_type_it_does_not_know(tmp_path):
    """A log written by a newer version loads without the events this version lacks."""
    store = FileRunStore(tmp_path)
    store.save_event("r", StepStarted(run_id="r", index=1))
    append_line(tmp_path / "r" / "events.jsonl", {"type": "from.the.future", "run_id": "r"})
    store.save_event("r", StepStarted(run_id="r", index=2))
    assert [event.index for event in store.load_events("r")] == [1, 2]


def test_a_study_is_an_artifact_key_of_the_file_store(tmp_path):
    """``study/<name>`` is a reference kind like ``design/<name>``."""
    store = FileRunStore(tmp_path)
    store.save_chat_artifact("c", "study/s", {"a": 1})
    assert store.load_chat_artifact("c", "study/s") == {"a": 1}


@pytest.mark.parametrize("make", [MemoryRunStore, lambda: FileRunStore("unused")])
def test_the_study_index_is_a_plain_chat_artifact_key(make, tmp_path):
    """``studies.index`` has no ``/``: it is a safe name in both stores, apart from any study."""
    store = FileRunStore(tmp_path) if make is not MemoryRunStore else make()
    store.save_chat_artifact("c", "studies.index", {"studies": []})
    assert store.load_chat_artifact("c", "studies.index") == {"studies": []}
    assert store.load_chat_artifact("c", "study/studies.index") is None
