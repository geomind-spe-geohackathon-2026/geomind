"""The checks pass on the shipped implementations and fail on broken ones."""

import pytest

import swarmax as sx
from swarmax.testing import check_run_store, check_workspace


def seed_history(store, chat_id, messages):
    """Fill a chat through the shipped stores' own method."""
    for message in messages:
        store.add_message(chat_id, message)


def test_memory_store_passes():
    """The memory store fulfils the contract."""
    check_run_store(sx.stores.MemoryRunStore, seed_history)


def test_file_store_passes(tmp_path):
    """The file store fulfils the contract, each check on a fresh folder."""
    counter = iter(range(100))
    check_run_store(lambda: sx.stores.FileRunStore(tmp_path / str(next(counter))), seed_history)


def workspace():
    """Return a filled memory workspace."""
    documents = {"p": [{"id": "1", "title": "Heat", "text": "heat pump"}]}
    return sx.stores.MemoryWorkspace({"p": object()}, documents)


def test_memory_workspace_passes():
    """The memory workspace fulfils the contract."""
    check_workspace(workspace, project="p", query="heat")


@pytest.fixture(scope="module")
def doublet():
    """Return a gemini plant; importing gemini takes more than the budget of one test call."""
    import gemini as gm

    return gm.plants.Doublet()


def test_file_workspace_passes(tmp_path, doublet):
    """The file workspace fulfils the contract, with a real gemini plant file."""
    project = tmp_path / "p"
    doublet.save(project / "plant.json")
    (project / "documents").mkdir()
    (project / "documents/report.md").write_text("heat pump heat")
    check_workspace(lambda: sx.stores.FileWorkspace(tmp_path), project="p", query="heat")


def test_a_store_that_loses_order_fails():
    """The check finds a broken store."""

    class Reversed(sx.stores.MemoryRunStore):
        def load_events(self, run_id):
            return list(reversed(super().load_events(run_id)))

    with pytest.raises(AssertionError, match="save order"):
        check_run_store(Reversed)


def test_a_store_that_keeps_old_state_fails():
    """A store that ignores the second save is caught."""

    class Sticky(sx.stores.MemoryRunStore):
        def save_state(self, chat_id, state):
            self.states.setdefault(chat_id, state)

    with pytest.raises(AssertionError, match="replace"):
        check_run_store(Sticky)


def test_a_workspace_that_finds_nothing_fails():
    """The check finds a broken workspace."""
    with pytest.raises(AssertionError, match="find the query"):
        check_workspace(
            lambda: sx.stores.MemoryWorkspace({"p": object()}), project="p", query="heat"
        )
