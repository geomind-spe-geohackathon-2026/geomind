"""The tools that read and store plants, against real gemini plants."""

import copy

import pytest

import geomind as gd
from geomind.stores import MemoryWorkspace
from geomind.tools.gemini.plants import apply_inputs
from tests.fixtures.calls import call
from tests.fixtures.sessions import StubSession

TOOLS = gd.tools.gemini


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


@pytest.fixture(scope="module")
def spec(gm):
    """Return the spec of gemini's example doublet heat plant, with its values."""
    return gm.plants.example("DoubletHeatPlant").to_dict()


@pytest.fixture
def broken(spec):
    """Return the example spec with its first connection removed, so two ports are open."""
    plant = copy.deepcopy(spec)
    plant["connections"] = plant["connections"][1:]
    return plant


def test_build_plant_offers_the_plant_schema_of_gemini(gm):
    """The model fills in gemini's own schema, its definitions at the top so references resolve."""
    schema = gm.plants.spec_schema()
    offered = TOOLS.build_plant.schema()["input_schema"]
    assert offered["properties"]["plant"]["properties"] == schema["properties"]
    assert offered["$defs"].items() >= schema.get("$defs", {}).items()
    assert "$defs" not in offered["properties"]["plant"]


async def test_list_plants_names_every_registered_plant_with_its_summary(gm):
    """The rows are gemini's names, in its order, with the summary it describes."""
    result = await call(TOOLS.list_plants, {})
    assert [row["name"] for row in result.output] == gm.plants.names()
    first = result.output[0]
    assert first == {
        "name": first["name"],
        "summary": gm.plants.get(first["name"]).describe()["summary"],
    }


async def test_read_plant_describes_the_project_plant_with_its_values(gm, spec):
    """Without a design, it is ``describe()`` of ``Workspace.plant``."""
    workspace = MemoryWorkspace(plants={"p1": gm.plants.from_dict(spec)})
    result = await call(TOOLS.read_plant, {}, StubSession(workspace=workspace), project="p1")
    assert not result.is_error
    plant = apply_inputs(gm.plants.from_dict(spec), spec)
    assert result.output == {**plant.describe(), "spec": spec}
    assert result.output["values"]["parameters"]


async def test_read_plant_without_a_project_says_so(gm):
    """A run with no project cannot read the project's plant."""
    result = await call(TOOLS.read_plant, {})
    assert result.output["error"]["code"] == "not_allowed"


async def test_read_plant_of_a_project_without_a_plant_says_so(gm):
    """A project with no plant is a result the model can act on."""
    session = StubSession(workspace=MemoryWorkspace())
    result = await call(TOOLS.read_plant, {}, session, project="p1")
    assert result.output["error"]["code"] == "unknown_name"


async def test_a_valid_plant_is_stored_and_read_back_by_its_reference(gm, spec):
    """``build_plant`` stores the plant under design/<name>; ``read_plant`` describes it."""
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": spec, "name": "base-1"}, session)
    assert built.output == {"design": "design/base-1", "problems": []}
    assert session.artifacts["design/base-1"] == spec
    read = await call(TOOLS.read_plant, {"design": "design/base-1"}, session)
    plant = apply_inputs(gm.plants.from_dict(spec), spec)
    assert read.output == {**plant.describe(), "spec": spec}


async def test_the_inputs_a_spec_keeps_are_applied(gm, spec):
    """The bridge: ``boundary[""]["inputs"]`` reaches the plant, which ``from_dict`` alone skips."""
    inputs = spec["boundary"][""]["inputs"]
    session = StubSession()
    await call(TOOLS.build_plant, {"plant": spec, "name": "base"}, session)
    read = await call(TOOLS.read_plant, {"design": "design/base"}, session)
    assert inputs == {"injection_pump": {"pressure_setpoint": 5150000.0}}
    assert read.output["values"]["controls"]["injection_pump.pressure_setpoint"] == 5150000.0


async def test_a_plant_with_problems_returns_them_and_stores_nothing(gm, broken):
    """The problems are gemini's own, from ``validate(on_error="record")``."""
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": broken, "name": "b"}, session)
    assert built.output == {
        "design": None,
        "problems": gm.plants.validate(broken, on_error="record"),
    }
    assert built.output["problems"][0]["code"] == "unconnected_port"
    assert session.artifacts == {}


@pytest.mark.parametrize("name", ["a/b", "", "../x", "a b"])
async def test_a_design_name_must_be_one_safe_name(spec, name):
    """The name becomes part of a store key, so it is checked before anything is stored."""
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": spec, "name": name}, session)
    assert built.output["error"]["code"] == "invalid_input"
    assert built.output["error"]["path"] == "name"
    assert session.artifacts == {}


async def test_read_plant_reads_a_registered_example_with_its_spec(gm):
    """``example/<Name>`` is ``gm.plants.example``: a start for a design, read only."""
    result = await call(TOOLS.read_plant, {"design": "example/HackathonPlant"})
    example = gm.plants.example("HackathonPlant")
    assert result.output == {**example.describe(), "spec": example.to_dict()}


async def test_read_plant_reads_a_template_with_its_spec(gm):
    """``template/<name>`` is ``gm.plants.from_template``, without values."""
    result = await call(TOOLS.read_plant, {"design": "template/heating_only"})
    assert result.output["spec"] == gm.plants.from_template("heating_only").to_dict()


@pytest.mark.parametrize("design", ["example/Hackathon", "template/heating"])
async def test_an_unknown_example_or_template_is_gemini_s_problem(gm, design):
    """The problem of gemini says which names exist."""
    result = await call(TOOLS.read_plant, {"design": design})
    assert result.is_error
    assert result.output["error"]["code"] != "internal"


@pytest.mark.parametrize("design", ["design/missing", "result/r1", "base-1"])
async def test_reading_an_unknown_design_is_unknown_name(gm, design):
    """Only a stored design reference reads back."""
    result = await call(TOOLS.read_plant, {"design": design})
    assert result.output["error"]["code"] == "unknown_name"
    assert result.output["error"]["path"] == "design"
