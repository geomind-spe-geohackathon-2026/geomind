"""Files written by earlier versions keep loading."""

import tarfile

import pytest

import geomind as gd
from geomind.providers import FakeLLM
from tests.fixtures import FIXTURES
from tests.fixtures.runs import says


@pytest.fixture
def stored(tmp_path):
    """Unpack one stored S1 run; return its store and run id."""
    with tarfile.open(FIXTURES / "stored/s1_run.tar.gz") as archive:
        archive.extractall(tmp_path, filter="data")
    run_id = next(path.name for path in tmp_path.iterdir())
    return gd.stores.FileRunStore(tmp_path), run_id


def test_a_stored_run_resumes(stored):
    """A run paused by S1 continues here, with the agent it named."""
    store, run_id = stored
    run = gd.Run.load(run_id, llm=FakeLLM([says("end")]), store=store)
    assert run.loop.agent.path == "assistant"
    result = run.resume("request-7", {"text": "water"})
    assert (result.status, result.answer) == ("done", "end")


async def test_a_stored_run_replays(stored):
    """Its log reruns up to where it paused."""
    store, run_id = stored
    assert (await gd.Engine.replay(store, run_id)).stop_reason == "cancelled"


def test_stored_options_load_in_the_new_shape(stored):
    """Plain strings stored by S1 are read as options, and answers still fit."""
    store, run_id = stored
    request = next(event for event in store.load_events(run_id) if event.type == "request")
    assert request.data()["options"][0] == {"value": "water", "label": "water"}


def test_a_stored_run_has_a_log(stored):
    """The contract's log builds from old events."""
    store, run_id = stored
    log = gd.runlog(store.load_events(run_id))
    assert log["run"]["status"] == "waiting" and log["steps"][0]["agent"] == "assistant"
