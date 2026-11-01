"""Stored designs and runs: what the gemini tools keep, read back as gemini objects."""

import json

import pytest

from geomind.context import ProblemState
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.tools.gemini.stored import load_design, load_run, save_design, save_run
from tests.fixtures.cases import SHALLOW_PEAK_HEATING, example_folder
from tests.fixtures.sessions import StubSession


async def shallow_context():
    """Return a context on the shallow example: its case in the state, its demand file stored."""
    import gemini as gm

    folder = example_folder("shallow_district")
    session = StubSession()
    await session.save_artifact("case/demand.csv", (folder / "demand.csv").read_bytes())
    problem = ProblemState(case=json.loads((folder / "case.json").read_text()))
    case = gm.Case.from_json(folder / "case.json")
    plant = gm.Plant.from_json(folder / "plant.json")
    return Context(session=session, problem=problem), plant, case


async def test_a_design_reads_back_with_its_inputs():
    """A stored design is the plant dict with its inputs; ``from_dict`` restores them."""
    context, plant, _ = await shallow_context()
    reference = await save_design(context, "start", plant)
    loaded = load_design(context, reference, "test")
    assert reference == "design/start"
    assert loaded.to_dict(structure=True) == plant.to_dict(structure=True)


async def test_a_run_reads_back_as_plant_case_and_results():
    """The plant, the case it ran on (its demand from the run's files) and the results."""
    import gemini as gm

    context, plant, case = await shallow_context()
    results = gm.simulate(plant, case)
    reference = await save_run(context, plant, results, {"steps": 1}, {})
    loaded_plant, loaded_case, loaded_results = load_run(context, reference, "test")
    assert reference.startswith("result/")
    assert loaded_plant.to_dict(structure=True) == plant.to_dict(structure=True)
    assert loaded_case.demand.frame["heating_demand"].max() == pytest.approx(SHALLOW_PEAK_HEATING)
    assert loaded_results.to_bytes() == results.to_bytes()


@pytest.mark.parametrize("reference", ["result/unknown", "design/x", "x"])
async def test_an_unknown_run_is_unknown_name(reference):
    """A reference that no run returned says so; the model can list what it has."""
    context, _, _ = await shallow_context()
    with pytest.raises(ToolError) as raised:
        load_run(context, reference, "check_results")
    assert raised.value.code == "unknown_name"


async def test_a_design_name_with_a_folder_is_refused():
    """A design name is one name: no path."""
    context, plant, _ = await shallow_context()
    with pytest.raises(ToolError, match="name = 'a/b'"):
        await save_design(context, "a/b", plant)
