"""The tools that read and store plants, against real gemini plants of both examples."""

import copy
import json

import pytest

import geomind as gd
from geomind.stores import MemoryWorkspace
from geomind.tools.gemini.plants import load_plant
from tests.fixtures.calls import call
from tests.fixtures.cases import example_folder
from tests.fixtures.sessions import StubSession

TOOLS = gd.tools.gemini
HACKATHON_PLANTS = (
    "HackathonPlant",
    "HeatingAbsorptionCoolingPlant",
    "HeatingCoolingPlant",
    "HeatingFullCoolingPlant",
    "HeatingHeatPumpCoolingPlant",
    "HeatingPlant",
)
PLANT_FILES = [("hackathon_2026", f"plants/{name}.json") for name in HACKATHON_PLANTS] + [
    ("shallow_district", "plant.json")
]
every_example_plant = pytest.mark.parametrize(
    ("example", "file"), PLANT_FILES, ids=[file for _, file in PLANT_FILES]
)


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def plant_dict(example, file):
    """Return an example plant file as the dict ``gm.Plant.to_dict(structure=True)`` writes."""
    import gemini as gm

    return gm.Plant.from_json(example_folder(example) / file).to_dict(structure=True)


def test_build_plant_offers_the_plant_schema_of_gemini(gm):
    """The model fills in gemini's own schema, its definitions at the top so references resolve."""
    schema = gm.plants.schema()
    offered = TOOLS.build_plant.schema()["input_schema"]
    assert offered["properties"]["plant"]["anyOf"] == schema["anyOf"]
    assert offered["$defs"].items() >= schema.get("$defs", {}).items()
    assert "$defs" not in offered["properties"]["plant"]


async def test_list_plants_names_every_class_with_its_summary_and_capabilities(gm):
    """The rows are gemini's names, in its order, and the capabilities are gemini's."""
    result = await call(TOOLS.list_plants, {})
    rows = result.output["plants"]
    assert [row["name"] for row in rows] == gm.plants.names()
    assert rows[0] == {
        "name": rows[0]["name"],
        "summary": gm.plants.get(rows[0]["name"]).describe()["summary"],
    }
    assert result.output["capabilities"] == gm.plants.capabilities()
    assert set(result.output["capabilities"]["HeatingPlant"]) == {"roles", "schedulable", "choices"}


@every_example_plant
async def test_a_stored_design_reads_back_as_its_dict_with_its_missing_parameters(example, file):
    """``read_plant`` of ``design/<name>`` is the plant dict and what gemini says is unset.

    A design may wait for what the case gives (the reservoir, the geotherm), so the list is
    gemini's own, not empty.
    """
    import gemini as gm

    data = plant_dict(example, file)
    session = StubSession()
    session.artifacts["design/x"] = data
    result = await call(TOOLS.read_plant, {"design": "design/x"}, session)
    assert not result.is_error
    assert result.output["plant"] == data
    assert result.output["missing_parameters"] == gm.Plant.from_dict(data).missing_parameters()


async def test_a_class_name_reads_as_a_plant_with_its_missing_parameters(gm):
    """A class has no values: the model reads what it must fill in."""
    result = await call(TOOLS.read_plant, {"design": "HeatingPlant"})
    plant = gm.plants.get("HeatingPlant")
    assert not result.is_error
    assert result.output["plant"] == plant.to_dict(structure=True)
    missing = result.output["missing_parameters"]
    assert missing == plant.missing_parameters()
    assert missing
    assert set(missing[0]) == {
        "path",
        "type",
        "quantity",
        "unit",
        "units",
        "minimum",
        "maximum",
        "enum",
        "description",
    }


async def test_an_unknown_class_name_is_gemini_s_problem_with_suggestions(gm):
    """A misspelt class gets gemini's close matches."""
    result = await call(TOOLS.read_plant, {"design": "HeatingPlnt"})
    assert result.is_error
    assert result.output["error"]["suggestions"][0] == "HeatingPlant"


@every_example_plant
async def test_build_plant_round_trips_each_example_plant(example, file):
    """A valid plant dict is stored as design/<name> and read back the same."""
    data = plant_dict(example, file)
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    assert built.output == {"design": "design/p", "problems": []}
    assert session.artifacts["design/p"] == data
    read = await call(TOOLS.read_plant, {"design": "design/p"}, session)
    assert read.output["plant"] == data


async def test_the_inputs_of_a_design_survive_storing(gm):
    """The inputs a plant dict keeps are restored by ``from_dict``, with no bridge."""
    data = plant_dict("shallow_district", "plant.json")
    assert data["inputs"]
    session = StubSession()
    await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    assert load_plant(_context(session), "design/p", "test").to_dict(structure=True)["inputs"] == (
        data["inputs"]
    )


def _context(session, project=None):
    """Return a tool context over ``session``."""
    from geomind.engine import Context

    return Context(session=session, project=project)


async def test_a_wrong_parameter_name_is_reported_with_gemini_s_path_and_suggestion():
    """The problem keeps gemini's path and did-you-mean, and nothing is stored."""
    data = plant_dict("hackathon_2026", "plants/HackathonPlant.json")
    params = data["modules"]["d0"]["params"]
    params["depht"] = params.pop("depth")
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    problem = built.output["problems"][0]
    assert built.output["design"] is None
    assert problem["path"] == "modules.d0.params.depht"
    assert problem["code"] == "unknown_name"
    assert problem["suggestions"] == ["depth"]
    assert session.artifacts == {}


async def test_a_value_with_a_unit_string_is_refused_by_gemini():
    """``"2500 m"`` is not a quantity; the model is told to give ``{value, unit}``."""
    data = plant_dict("hackathon_2026", "plants/HackathonPlant.json")
    data["modules"]["d0"]["params"]["depth"] = "2500 m"
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    problem = built.output["problems"][0]
    assert built.output["design"] is None
    assert problem["path"] == "modules.d0.params.depth"
    assert problem["code"] == "invalid_value"
    assert session.artifacts == {}


@pytest.mark.parametrize("name", ["a/b", "", "../x", "a b"])
async def test_a_design_name_must_be_one_safe_name(name):
    """The name becomes part of a store key, so it is checked before anything is stored."""
    data = plant_dict("shallow_district", "plant.json")
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": name}, session)
    assert built.output["error"]["code"] == "invalid_input"
    assert built.output["error"]["path"] == "name"
    assert session.artifacts == {}


@pytest.mark.parametrize("design", ["design/missing", "result/r1"])
async def test_reading_an_unknown_design_reference_is_unknown_name(design):
    """Only a stored design reference reads back; ``result/`` is no design."""
    result = await call(TOOLS.read_plant, {"design": design})
    assert result.output["error"]["code"] == "unknown_name"


@every_example_plant
async def test_read_plant_of_the_project_is_its_dict(example, file):
    """Without a design, it is the workspace plant's dict, the plant object left unchanged."""
    import gemini as gm

    plant = gm.Plant.from_json(example_folder(example) / file)
    before = copy.deepcopy(plant.to_dict(structure=True))
    workspace = MemoryWorkspace(plants={"p1": plant})
    result = await call(TOOLS.read_plant, {}, StubSession(workspace=workspace), project="p1")
    assert result.output["plant"] == before
    assert plant.to_dict(structure=True) == before
    json.dumps(result.output)


async def test_read_plant_without_a_project_says_so():
    """A run with no project cannot read the project's plant."""
    result = await call(TOOLS.read_plant, {})
    assert result.output["error"]["code"] == "not_allowed"


async def test_read_plant_of_a_project_without_a_plant_says_so():
    """A project with no plant is a result the model can act on."""
    session = StubSession(workspace=MemoryWorkspace())
    result = await call(TOOLS.read_plant, {}, session, project="p1")
    assert result.output["error"]["code"] == "unknown_name"
