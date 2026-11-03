"""Two runs of one chat share its artifacts: case files, designs and results."""

import json

import pytest

from geomind import runtime
from geomind.agents import Agent
from geomind.engine import Permissions
from geomind.prompts import Prompt
from geomind.providers import FakeLLM
from geomind.run import Run
from geomind.stores import FileRunStore, MemoryRunStore, MemoryWorkspace
from geomind.tools.gemini.assessment import check_results
from geomind.tools.gemini.case import set_case
from geomind.tools.gemini.plants import build_plant
from geomind.tools.gemini.results import read_result
from geomind.tools.gemini.runs import simulate
from geomind.types import ToolCall
from tests.fixtures.cases import example_case, example_plant_files
from tests.fixtures.runs import STEPS, call, of_type, says, uses

PLANT_FILE = "plants/HeatingHeatPumpCoolingPlant.json"
CASE_FILE = "case/data/demand.csv"


class DesignLead(Agent):
    """Uses the tools that keep case files, designs and results."""

    def __init__(self):
        """Declare the tools."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Design.")

        # Tools
        self.set_case = set_case
        self.build_plant = build_plant
        self.simulate = simulate
        self.read_result = read_result
        self.check_results = check_results


def named(tool, call_id, **tool_input):
    """Return a call whose input has a ``name``."""
    return ToolCall(id=call_id, name=tool, input=tool_input)


def workspace():
    """Return a workspace holding the shallow example as project ``p``."""
    return MemoryWorkspace(cases={"p": example_case("shallow_district")})


def message(store, completions, chat="chat"):
    """Run one message of a chat; return the run and its tool results by call id."""
    run = Run(
        "go",
        chat=chat,
        project="p",
        llm=FakeLLM(completions),
        store=store,
        workspace=workspace(),
        permissions=Permissions("auto"),
        agent=DesignLead(),
    )
    with runtime.settings(max_steps=STEPS):
        run.start()
    results = of_type(store.load_events(run.id), "tool.result")
    return run, {event.call_id: event.output for event in results}


@pytest.fixture(scope="module")
def plant_file():
    """Return the plant file of the shallow example."""
    return json.loads(example_plant_files("shallow_district")[PLANT_FILE])


@pytest.fixture(scope="module")
def first(plant_file):
    """Return the store after the first message: a case, a design and a simulated result."""
    store = MemoryRunStore()
    script = [
        uses(call("set_case", "c1", source="project")),
        uses(named("build_plant", "c2", plant=plant_file, name="start")),
        uses(call("simulate", "c3", design="design/start")),
        says(),
    ]
    run, results = message(store, script)
    return store, run, results


def test_the_first_message_keeps_its_artifacts_in_the_chat_space(first):
    """The case file, the design and the result are the chat's."""
    store, run, results = first
    assert "error" not in results["c3"]
    assert store.load_chat_artifact("chat", CASE_FILE)
    assert store.load_chat_artifact("chat", "design/start")
    assert store.load_chat_artifact("chat", results["c3"]["reference"])
    assert store.load_artifact(run.id, "design/start") is None


@pytest.fixture(scope="module")
def second(first):
    """Return the results of the second message of the chat, which reads the first's."""
    store, _, results = first
    reference = results["c3"]["reference"]
    script = [
        uses(
            call("check_results", "d1", reference=reference),
            call("read_result", "d2", reference=reference),
            call("simulate", "d3", design="design/start"),
        ),
        says(),
    ]
    return message(store, script)[1]


def test_the_second_message_checks_and_reads_the_first_result(second):
    """The result, its case files and its plant are readable in another run of the chat."""
    assert "feasible" in second["d1"]
    assert "error" not in second["d2"]


def test_the_second_message_simulates_the_first_design_on_the_case_files(second, first):
    """The design and the demand file of the first message are there."""
    assert second["d3"]["reference"] == first[2]["c3"]["reference"]


def test_another_chat_does_not_read_the_artifacts(first):
    """The space is the chat's."""
    store, _, results = first
    other = message(
        store,
        [uses(call("check_results", "e1", reference=results["c3"]["reference"])), says()],
        "x",
    )[1]
    assert other["e1"]["error"]["code"] == "unknown_name"


def test_a_design_name_is_written_once(first, plant_file):
    """The same content again is fine; other content asks for a new name."""
    store = first[0]
    changed = json.loads(json.dumps(plant_file))
    changed["name"] = "another plant"
    script = [
        uses(named("build_plant", "f1", plant=plant_file, name="start")),
        uses(named("build_plant", "f2", plant=changed, name="start")),
        says(),
    ]
    results = message(store, script)[1]
    assert "error" not in results["f1"]
    assert "use a new name" in results["f2"]["error"]["message"]
    assert results["f2"]["error"]["suggestions"] == ["start_2"]


def test_a_run_without_a_chat_is_the_chat_of_its_root_run():
    """Nothing changes for a CLI run: its artifacts are readable in its own session."""
    store = MemoryRunStore()
    script = [uses(call("set_case", "g1", source="project")), says()]
    run = Run(
        "go",
        project="p",
        llm=FakeLLM(script),
        store=store,
        workspace=workspace(),
        permissions=Permissions("auto"),
        agent=DesignLead(),
    )
    run.start()
    assert store.load_chat_artifact(run.id, CASE_FILE)


def test_the_file_store_keeps_the_chat_space_on_disk(tmp_path):
    """The layout is ``<root>/chats/<chat id>/artifacts``."""
    store = FileRunStore(tmp_path)
    message(store, [uses(call("set_case", "h1", source="project")), says()], "disk")
    assert (tmp_path / "chats/disk/artifacts/case/data/demand.csv.bin").is_file()
