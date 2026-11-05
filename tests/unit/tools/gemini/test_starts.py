"""Starting plants: the Knowledge base's plant files, listed and stored as designs by name."""

from geomind.stores import MemoryWorkspace
from geomind.stores.knowledge import MemoryKnowledge
from geomind.tools.gemini.starts import list_starts, start_plant
from tests.fixtures.calls import call
from tests.fixtures.cases import example_folder
from tests.fixtures.sessions import StubSession

SUPERSTRUCTURE = "hackathon_superstructure/plants/HackathonSuperstructure.json"
PLANT = "hackathon_2026/plants/HeatingFullCoolingPlant.json"


def session_with_starts():
    """Return a session whose Knowledge base holds a superstructure, a plant and a text."""
    root = example_folder("")
    documents = {
        "plants/HackathonSuperstructure.json": (root / SUPERSTRUCTURE).read_bytes(),
        "HeatingFullCoolingPlant.json": (root / PLANT).read_bytes(),
        "prices.json": b'{"electricity": 1}',
        "brief.md": b"Brief\n\nNo plant here.",
    }
    return StubSession(workspace=MemoryWorkspace(knowledge=MemoryKnowledge(documents)))


async def test_list_starts_names_the_plant_files_of_the_knowledge_base():
    """A JSON document gemini reads as a plant is a start; any other document is not."""
    listed = (await call(list_starts, {}, session_with_starts())).output
    found = {item["start"]: item for item in listed}
    assert set(found) == {"HackathonSuperstructure", "HeatingFullCoolingPlant"}
    superstructure = found["HackathonSuperstructure"]
    assert superstructure["structures"] > 1 and "evolve_structure" in superstructure["note"]
    assert superstructure["document"] == "knowledge/plants/HackathonSuperstructure.json"
    assert found["HeatingFullCoolingPlant"]["structures"] == 1


async def test_start_plant_stores_the_superstructure_and_names_the_next_calls():
    """No plant file is typed: the design is the start's, then size_plant and one evolve."""
    session = session_with_starts()
    result = await call(start_plant, {"start": "HackathonSuperstructure", "name": "s"}, session)
    output = result.output
    assert output["design"] == "design/s" and "design/s" in session.artifacts
    assert output["structures"] > 1
    assert output["next"].startswith("size_plant(design='design/s'")
    assert "ONE evolve_structure" in output["next"]


async def test_an_unknown_start_names_the_starts():
    """A name that is no start lists them; without a Knowledge base it says there is none."""
    session = session_with_starts()
    result = await call(start_plant, {"start": "Superstructure", "name": "s"}, session)
    error = result.output["error"]
    assert error["code"] == "unknown_name" and "HackathonSuperstructure" in error["message"]
    result = await call(start_plant, {"start": "x", "name": "s"}, StubSession())
    assert "holds no plant file" in result.output["error"]["message"]
    assert (await call(list_starts, {}, StubSession())).output == []
