"""The checks pass on the shipped implementations and fail on broken ones."""

import shutil

import pytest

import geomind as gd
from geomind.testing import check_run_store, check_workspace
from tests.fixtures.cases import example_case, example_folder


def seed_history(store, chat_id, messages):
    """Fill a chat through the shipped stores' own method."""
    for message in messages:
        store.add_message(chat_id, message)


def test_memory_store_passes():
    """The memory store fulfils the contract."""
    check_run_store(gd.stores.MemoryRunStore, seed_history)


def test_file_store_passes(tmp_path):
    """The file store fulfils the contract, each check on a fresh folder."""
    counter = iter(range(100))
    check_run_store(lambda: gd.stores.FileRunStore(tmp_path / str(next(counter))), seed_history)


PLANTS = {"P": {"kind": "plant"}}


def workspace():
    """Return a filled memory workspace."""
    documents = {"p": [{"id": "1", "title": "Heat", "text": "heat pump"}]}
    cases = {"p": example_case("shallow_district")}
    return gd.stores.MemoryWorkspace({"p": PLANTS}, documents, cases)


def test_memory_workspace_passes():
    """The memory workspace fulfils the contract."""
    check_workspace(workspace, project="p", query="heat")


def test_file_workspace_passes(tmp_path):
    """The file workspace fulfils the contract, with gemini's project folder of an example."""
    project = tmp_path / "p"
    shutil.copytree(example_folder("shallow_district"), project)
    (project / "documents").mkdir()
    (project / "documents/report.md").write_text("heat pump heat")
    check_workspace(lambda: gd.stores.FileWorkspace(tmp_path), project="p", query="heat")


def test_a_store_that_loses_order_fails():
    """The check finds a broken store."""

    class Reversed(gd.stores.MemoryRunStore):
        def load_events(self, run_id):
            return list(reversed(super().load_events(run_id)))

    with pytest.raises(AssertionError, match="sequence order"):
        check_run_store(Reversed)


def test_a_store_without_load_events_fails():
    """The method is part of the contract now."""

    class Partial:
        def save_event(self, run_id, event):
            """Accept events and nothing else."""

    with pytest.raises(AssertionError, match="load_events"):
        check_run_store(Partial)


def test_a_store_that_keeps_old_state_fails():
    """A store that ignores the second save is caught."""

    class Sticky(gd.stores.MemoryRunStore):
        def save_state(self, chat_id, state):
            self.states.setdefault(chat_id, state)

    with pytest.raises(AssertionError, match="replace"):
        check_run_store(Sticky)


def test_a_workspace_that_finds_nothing_fails():
    """The check finds a broken workspace."""
    with pytest.raises(AssertionError, match="find the query"):
        check_workspace(
            lambda: gd.stores.MemoryWorkspace(
                {"p": PLANTS}, cases={"p": example_case("shallow_district")}
            ),
            project="p",
            query="heat",
        )


def test_a_workspace_without_a_case_fails():
    """The case of the project is part of the contract."""

    class NoCase(gd.stores.MemoryWorkspace):
        def case(self, project_id):
            return None

    with pytest.raises(AssertionError, match="case must load"):
        check_workspace(lambda: NoCase({"p": PLANTS}, {"p": []}), project="p", query="heat")


def test_a_store_that_loses_case_files_fails():
    """A case file is bytes under ``case/<file name>``."""

    class Lossy(gd.stores.MemoryRunStore):
        def save_artifact(self, run_id, key, data):
            if not key.startswith("case/"):
                super().save_artifact(run_id, key, data)

    with pytest.raises(AssertionError, match="case/<file name>"):
        check_run_store(Lossy)


def test_a_workspace_that_forgets_a_case_file_fails():
    """Every file the case names, the economics too, comes with the case."""

    class Forgetful(gd.stores.MemoryWorkspace):
        def case(self, project_id):
            data, files = super().case(project_id)
            return data, {
                name: content for name, content in files.items() if name != "economics.json"
            }

    with pytest.raises(AssertionError, match="economics.json"):
        check_workspace(
            lambda: Forgetful({"p": PLANTS}, {"p": []}, {"p": example_case("shallow_district")}),
            project="p",
            query="heat",
        )


def test_a_workspace_with_an_unsafe_file_name_fails():
    """A case file name is a relative path inside the project."""
    data, files = example_case("shallow_district")
    unsafe = workspace_with({"../demand.csv": b"x", **files}, data)
    with pytest.raises(AssertionError, match="relative path"):
        check_workspace(lambda: unsafe, project="p", query="heat")


def workspace_with(files, data):
    """Return a memory workspace whose case has these files."""
    documents = {"p": [{"id": "1", "title": "Heat", "text": "heat"}]}
    return gd.stores.MemoryWorkspace({"p": PLANTS}, documents, {"p": (data, files)})


def test_a_workspace_without_plants_fails():
    """The plant files of the project are part of the contract."""
    with pytest.raises(AssertionError, match="plants must be"):
        check_workspace(
            lambda: gd.stores.MemoryWorkspace(
                cases={"p": example_case("shallow_district")},
                documents={"p": [{"id": "1", "title": "Heat", "text": "heat"}]},
            ),
            project="p",
            query="heat",
        )
