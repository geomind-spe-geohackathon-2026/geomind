"""Every recording of ``evals/recordings`` replays offline, so one that stops replaying fails."""

import asyncio

import pytest

from evals import run as evals
from geomind.engine import Engine
from geomind.stores import FileRunStore
from tests.integration.test_evals import gemini_loaded  # noqa: F401


@pytest.fixture
def stored(monkeypatch, tmp_path):
    """Run tasks into one folder store each, and return what a replay of them needs."""
    made = []
    real_new_run = evals.new_run

    def new_run(task, agent_name, llm, store, loop=None):
        folder = tmp_path / f"task{len(made)}"
        folder.mkdir()
        file_store = FileRunStore(folder)
        made.append((file_store, folder, evals._workspace(task)[0]))
        return real_new_run(task, agent_name, llm, file_store, loop)

    monkeypatch.setattr(evals, "new_run", new_run)
    return made


async def replay_all(made):
    """Replay every root run of every stored task; a run that differs raises ``ReplayError``."""
    count = 0
    for store, folder, workspace in made:
        for root in (path.name for path in folder.iterdir() if path.name != "chats"):
            await Engine.replay(store, root, workspace=workspace)
            count += 1
    return count


@pytest.mark.parametrize("agent", ["analyst", "designer", "explainer", "coordinator"])
def test_the_recordings_of_a_single_agent_replay(gemini_loaded, stored, agent):  # noqa: F811
    """Each task of the agent runs from its recording into a store, and that run replays."""
    outcomes = evals.run_agent(agent)
    assert asyncio.run(replay_all(stored)) == len(outcomes) > 0


@pytest.mark.slow
@pytest.mark.parametrize("suite", ["challenge2", "compare"])
def test_the_recordings_of_a_loop_suite_replay(gemini_loaded, stored, suite):  # noqa: F811
    """Each task of the suite runs through its loop into a store, and that run replays.

    NOTE: slow, because the loops simulate a year in each task.
    """
    outcomes = evals.run_agent(suite)
    assert asyncio.run(replay_all(stored)) == len(outcomes) > 0
