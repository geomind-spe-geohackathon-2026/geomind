"""A design run on a project with attached files fills the case from them, without asking."""

from pathlib import Path

import pytest

from geomind.agents import DesignLead, Reviewer
from geomind.context import ProblemState
from geomind.engine import Engine
from geomind.engine.recovery import recover
from geomind.loops import DesignLoop
from geomind.stores import MemoryWorkspace
from geomind.types import ToolCall
from tests.fixtures.runs import context, engine_for, of_type, says, uses
from tests.unit.loops.test_design import PASSED, designer_round, verifier_round

FILES = Path(__file__).parents[1] / "fixtures" / "files"
CASE = {
    "format": 1,
    "kind": "case",
    "name": "attached",
    "time": {
        "start": "2030-01-01",
        "end": "2030-01-14",
        "step": {"value": 1, "unit": "d"},
    },
    "demand": {
        "heating": {
            "power": {"unit": "MW", "file": "demand.csv", "column": "heat_mw"},
            "supply_temperature": {"value": 60, "unit": "degC"},
            "return_temperature": {"value": 40, "unit": "degC"},
        }
    },
}
SCRIPT = [
    uses(ToolCall(id="f1", name="list_files", input={})),
    uses(ToolCall(id="f2", name="read_document", input={"name": "demand.csv"})),
    uses(ToolCall(id="f3", name="read_document", input={"name": "requirements.pdf"})),
    uses(ToolCall(id="f4", name="set_case", input={"changes": CASE, "files": ["demand.csv"]})),
    *designer_round(1),
    *verifier_round(1),
    says("costs"),
    says("explained"),
]


def attached():
    """Return a workspace whose project holds a demand CSV and a requirements PDF."""
    held = {path.name: path.read_bytes() for path in FILES.iterdir()}
    return MemoryWorkspace(files={"p": held})


@pytest.fixture
def passed(monkeypatch):
    """Let gemini's verdict pass, so the run ends without a question."""
    monkeypatch.setattr("geomind.agents.project.drivers.verify_design", lambda _: PASSED)
    monkeypatch.setattr("geomind.engine.hooks.verify_design", lambda _: PASSED)


async def run_on_files():
    """Run the scripted design loop on the attached files; return its result and engine."""
    workspace = attached()
    engine = engine_for(SCRIPT, workspace=workspace)
    start = context("Design a plant from the attached files.", problem=ProblemState(), project="p")
    result = await DesignLoop(DesignLead(), Reviewer()).run(engine, start)
    return result, engine, workspace


async def test_the_loop_fills_the_case_from_the_files_without_asking(passed):
    """The design lead reads both files, the case takes the CSV's bytes, and nobody is asked."""
    result, engine, _ = await run_on_files()
    events = engine.store.load_events(result.run_id)
    assert result.status == "done"
    assert not of_type(events, "request")
    pdf = [e for e in of_type(events, "tool.result") if e.tool == "read_document"][1]
    assert "Supply temperature" in pdf.output["text"]
    assert recover(events).problem.case["demand"]["heating"]["power"]["file"] == "demand.csv"


async def test_the_run_replays(passed):
    """The files reach the replay through the workspace, as a project's case does."""
    result, engine, workspace = await run_on_files()
    replayed = await Engine.replay(engine.store, result.run_id, workspace=workspace)
    assert replayed.answer == result.answer
