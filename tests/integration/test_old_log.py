"""A 0.3.1 log with a ``run_study`` call loads and exports; its replay names the changed driver."""

import asyncio
import tarfile
from pathlib import Path

import pytest

from geomind.engine import Engine, replay
from geomind.errors import ReplayError
from geomind.export import render_export
from geomind.stores import FileRunStore, FileWorkspace
from geomind.types.events import ToolRecorded
from geomind.utils.json import read_json
from tests.fixtures import ROOT

ARCHIVE = ROOT / "tests" / "fixtures" / "logs" / "compare_0_3_1.tar.gz"
PROJECTS = ROOT / "evals" / "projects"

pytestmark = pytest.mark.slow


@pytest.fixture(scope="module")
def stored(tmp_path_factory):
    """Return ``(store, run id, run folder)`` of the 0.3.1 compare run, extracted once.

    NOTE: the log was made by the code of commit a38bad6 from ``evals/recordings/compare/
    two_families.jsonl`` as it was then, so its ``run_study`` call has no ``name``. The archive
    holds the whole events log, the manifest and the five artifacts the replay reads (the final
    result and its plant, case and files, and the best design); each other artifact was dropped
    after a replay without it still passed. The archive was packed on macOS, and its ``._*``
    metadata entries are no part of the log, so they stay out of the extracted folder.
    """
    root = tmp_path_factory.mktemp("log")
    with tarfile.open(ARCHIVE) as archive:
        members = [item for item in archive if not Path(item.name).name.startswith("._")]
        archive.extractall(root, members=members, filter="data")
    run_id = next(path.name for path in root.iterdir() if path.name != "chats")
    return FileRunStore(root), run_id, root / run_id


@pytest.fixture
def newer_geomind(monkeypatch):
    """Make the current geomind version differ from the recorded one, as 0.4.0 does."""
    current = replay.current_versions
    monkeypatch.setattr(replay, "current_versions", lambda: {**current(), "geomind": "9.9.9"})


def test_the_log_loads_and_has_a_study_call_without_a_name(stored):
    """The events load, and the recorded ``run_study`` input fails today's schema."""
    store, run_id, _ = stored
    events = store.load_events(run_id)
    (study,) = [e for e in events if isinstance(e, ToolRecorded) and e.tool == "run_study"]
    assert "name" not in study.input
    assert not [e for e in events if e.type == "study.recorded"]


def test_the_log_replays_up_to_the_driver_s_first_changed_decision(stored, newer_geomind):
    """The driver's rules changed since 0.3.1, so the replay stops at its first move, named.

    NOTE: the 0.3.1 driver asked the user for a missing case and delegated to ``designer`` and
    ``verifier``; today's loads the project's case file by rule (fdbfed8) and delegates to
    ``design_lead`` and ``reviewer``, so the whole tree no longer replays. A replay checks the
    decisions, so it raises ``ReplayError`` on the driver, not a schema error on the recorded
    ``run_study`` input; that a reused call skips today's schema is pinned by
    ``tests/unit/engine/test_replay.py``.
    """
    store, run_id, _ = stored
    with pytest.raises(ReplayError, match=rf"run {run_id} \(compare_driver\): .*replayed 0"):
        asyncio.run(Engine.replay(store, run_id, workspace=FileWorkspace(PROJECTS)))


def test_the_log_exports_with_its_study_call(stored):
    """The export shows the tool call as the model made it."""
    store, run_id, folder = stored
    text = render_export(store.load_events(run_id), read_json(folder / "run_manifest.json"))
    assert "- run_study(" in text
