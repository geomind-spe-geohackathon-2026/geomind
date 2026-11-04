"""Every recording of ``evals/recordings`` replays offline, so one that stops replaying fails."""

import asyncio

import pytest

from evals import run as evals
from geomind.engine import Engine
from geomind.stores import FileRunStore
from tests.integration.test_evals import gemini_loaded  # noqa: F401

GEMINI_WORK = {"project_plant", "missing_range"}
"""Single-agent tasks whose recording sizes a plant or searches 30 evaluations for real."""


@pytest.fixture
def stored(monkeypatch, tmp_path):
    """Run tasks into one folder store each, and return what a replay of them needs."""
    made = []
    real_new_run = evals.new_run

    def new_run(task, agent_name, llm, store, loop=None, hooks=()):
        folder = tmp_path / f"task{len(made)}"
        folder.mkdir()
        file_store = FileRunStore(folder)
        made.append((file_store, folder, evals._workspace(task)[0]))
        return real_new_run(task, agent_name, llm, file_store, loop, hooks)

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


def tasks(agents):
    """Return one test parameter per task file of the task folders ``agents``.

    A task that sizes or searches with gemini runs in the slow tier.
    """
    return [
        pytest.param(
            agent,
            path.stem,
            id=f"{agent}-{path.stem}",
            marks=[pytest.mark.slow] if path.stem in GEMINI_WORK else [],
        )
        for agent in agents
        for path in sorted((evals.ROOT / "tasks" / agent).glob("*.yaml"))
    ]


def run_and_replay(stored, agent, name):
    """Run one task from its recording into a store, and replay it."""
    path = evals.ROOT / "tasks" / agent / f"{name}.yaml"
    llm = evals.FakeLLM.from_recording(evals.ROOT / "recordings" / agent / f"{name}.jsonl")
    evals.run_task(name, evals.load_task(path), agent, llm)
    assert asyncio.run(replay_all(stored)) == 1


@pytest.mark.parametrize(
    ("agent", "name"), tasks(["analysis_lead", "design_lead", "explainer", "coordinator"])
)
@pytest.mark.usefixtures("gemini_loaded")
def test_the_recording_of_a_single_agent_task_replays(stored, agent, name):
    """The task runs from its recording into a store, and that run replays."""
    run_and_replay(stored, agent, name)


@pytest.mark.slow
@pytest.mark.parametrize(("agent", "name"), tasks(["challenge2", "compare", "alternatives"]))
@pytest.mark.usefixtures("gemini_loaded")
def test_the_recording_of_a_loop_task_replays(stored, agent, name):
    """The task runs through its loop into a store, and that run replays.

    NOTE: slow, because the loops simulate a year in each task.
    """
    run_and_replay(stored, agent, name)
