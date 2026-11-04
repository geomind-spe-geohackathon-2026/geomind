"""A 0.3.1 log is read: it loads, shows and exports; only its replay says it cannot be re-run."""

import asyncio
import json
import tarfile
from pathlib import Path

import pytest

from geomind import cli
from geomind.engine import Engine, replay
from geomind.engine.recovery import agent_class
from geomind.errors import ReplayError
from geomind.export import render_export
from geomind.stores import FileRunStore, FileWorkspace
from geomind.types.events import ToolRecorded
from geomind.types.runlog import runlog
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


def test_the_log_names_classes_that_exist_today(stored):
    """Each run's 0.3.1 class path is found today through ``RENAMED_CLASSES``."""
    store, run_id, _ = stored
    started = [e for e in store.load_events(run_id) if e.type == "run.started"]
    classes = {e.agent: agent_class(e).__name__ for e in started}
    assert classes == {
        "compare_driver": "CompareDriver",
        "designer": "DesignLead",
        "verifier": "Reviewer",
        "economist": "Economist",
        "explainer": "Explainer",
    }


def test_the_replay_says_the_log_predates_the_case_lead(stored, newer_geomind):
    """The log is read but not re-run: the replay names its version and the case lead's.

    NOTE: the 0.3.1 driver asked the user for a missing case and delegated to ``designer`` and
    ``verifier``; today's loads the project's case file by rule (fdbfed8) and delegates to
    ``design_lead`` and ``reviewer`` (742e122), and the case lead sets the case (efb1066), so the
    tree no longer replays. The message keeps the first difference, on the driver; that a reused
    call skips today's schema is pinned by ``tests/unit/engine/test_replay.py``.
    """
    store, run_id, _ = stored
    message = (
        r"this log was recorded by geomind 0\.3\.1 before the case lead \(0\.4\.22\.dev7\); "
        r"it can be read, shown and exported, but not re-run "
        rf"\(first difference: .*run {run_id} \(compare_driver\): .*replayed 0"
    )
    with pytest.raises(ReplayError, match=message):
        asyncio.run(Engine.replay(store, run_id, workspace=FileWorkspace(PROJECTS)))


def test_the_log_shows_as_text_and_markdown(stored, capsys):
    """``geomind show`` prints the log, in text and in Markdown, with the study call."""
    _, run_id, folder = stored
    assert cli.main(["show", str(folder)]) == 0
    text = capsys.readouterr().out
    assert text.startswith(f"Run {run_id}: ") and "Tool run_study" in text
    assert cli.main(["show", str(folder), "--format", "md"]) == 0
    assert "- run_study(" in capsys.readouterr().out


def test_the_log_exports_as_json(stored):
    """The run log of the events is JSON, with every step of the tree."""
    store, run_id, _ = stored
    log = json.loads(json.dumps(runlog(store.load_events(run_id))))
    assert log["run"]["id"] == run_id
    assert len(log["steps"]) == 26
    assert any(c["tool"] == "run_study" for step in log["steps"] for c in step["tool_calls"])


def test_the_log_exports_with_its_study_call(stored):
    """The export shows the tool call as the model made it."""
    store, run_id, folder = stored
    text = render_export(store.load_events(run_id), read_json(folder / "run_manifest.json"))
    assert "- run_study(" in text
