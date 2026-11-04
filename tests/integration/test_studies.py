"""A study tool in a run: the event, the listing, and a log from before the event."""

import json

import pytest

from geomind import runtime
from geomind.agents import Agent
from geomind.engine import Engine, Permissions
from geomind.export import render_export
from geomind.prompts import Prompt
from geomind.providers import FakeLLM
from geomind.run import Run
from geomind.stores import MemoryRunStore, MemoryWorkspace
from geomind.tools.gemini.case import set_case
from geomind.tools.gemini.plants import build_plant
from geomind.tools.gemini.studies import list_studies, read_study
from geomind.tools.gemini.study import size_plant
from geomind.types import ToolCall
from tests.fixtures.cases import example_case, example_plant_files
from tests.fixtures.runs import STEPS, of_type, says, uses

PLANT_FILE = "plants/HeatingHeatPumpCoolingPlant.json"

pytestmark = pytest.mark.slow


class Sizer(Agent):
    """Sizes a design and reads the studies back."""

    def __init__(self):
        """Declare the tools."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Design.")

        # Tools
        self.set_case = set_case
        self.build_plant = build_plant
        self.size_plant = size_plant
        self.list_studies = list_studies
        self.read_study = read_study


def workspace():
    """Return a workspace holding the shallow example as project ``p``."""
    return MemoryWorkspace(cases={"p": example_case("shallow_district")})


def named(tool, call_id, **tool_input):
    """Return a call with its input."""
    return ToolCall(id=call_id, name=tool, input=tool_input)


@pytest.fixture(scope="module")
def recorded():
    """Return ``(store, run id)`` of a run that sizes a design and lists and reads its study."""
    plant = json.loads(example_plant_files("shallow_district")[PLANT_FILE])
    script = [
        uses(named("set_case", "c1", source="project")),
        uses(named("build_plant", "c2", plant=plant, name="start")),
        uses(named("size_plant", "c3", design="design/start", name="sizing")),
        uses(named("list_studies", "c4"), named("read_study", "c5", study="study/sizing")),
        says("study/sizing sized it"),
    ]
    store = MemoryRunStore()
    run = Run(
        "size it",
        chat="chat",
        project="p",
        llm=FakeLLM(script),
        store=store,
        workspace=workspace(),
        permissions=Permissions("auto"),
        agent=Sizer(),
    )
    with runtime.settings(max_steps=STEPS):
        run.start()
    return store, run.id


def test_the_event_comes_once_after_the_tool_starts_and_before_it_finishes(recorded):
    """``study.recorded`` names the call, the study and its plants, between start and finish."""
    store, run_id = recorded
    events = store.load_events(run_id)
    kinds = [event.type for event in events]
    (study,) = of_type(events, "study.recorded")
    assert study.data()["call_id"] == "c3" and study.data()["study"] == "study/sizing"
    assert (study.tool, study.method, study.designs) == ("size_plant", "run", ("start",))
    assert study.best == "design/sizing" and study.run == run_id
    started = next(
        i for i, e in enumerate(events) if e.type == "tool.started" and e.call_id == "c3"
    )
    finished = next(
        i for i, e in enumerate(events) if e.type == "tool.result" and e.call_id == "c3"
    )
    assert started < kinds.index("study.recorded") < finished


def test_the_study_is_listed_and_read_back_in_the_same_run(recorded):
    """``list_studies`` shows it as current and ``read_study`` returns what was stored."""
    store, run_id = recorded
    results = {e.call_id: e.output for e in of_type(store.load_events(run_id), "tool.result")}
    assert results["c3"]["study"] == "study/sizing"
    assert results["c4"] == [
        {
            "study": "study/sizing",
            "tool": "size_plant",
            "method": "run",
            "designs": ["start"],
            "best": "design/sizing",
            "current": True,
        }
    ]
    assert results["c5"]["designs"] == {"read": ["design/start"], "wrote": ["design/sizing"]}


def old_store(recorded):
    """Return a store holding the log as 0.3.1 wrote it: without ``study.recorded``."""
    store, run_id = recorded
    old = MemoryRunStore()
    for event in store.load_events(run_id):
        if event.type != "study.recorded":
            old.save_event(run_id, event)
    old.chat_artifacts = store.chat_artifacts
    return old


def test_a_log_without_the_study_event_replays_and_exports(recorded):
    """Replay compares the calls, so a missing event changes nothing; the export shows the keys."""
    import asyncio

    _, run_id = recorded
    replayed = []
    result = asyncio.run(
        Engine.replay(old_store(recorded), run_id, replayed=replayed, workspace=workspace())
    )
    assert result.status == "done"
    assert len(of_type(replayed, "study.recorded")) == 1
    text = render_export(old_store(recorded).load_events(run_id))
    assert 'size_plant({"design": "design/start", "name": "sizing"})' in text
    assert 'read_study({"study": "study/sizing"})' in text
