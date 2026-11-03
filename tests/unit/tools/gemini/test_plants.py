"""The tools that read and store plants, against real gemini plants of both examples."""

import asyncio
import copy
import json
import shutil

import gemini
import pytest

import geomind as gd
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.stores import FileWorkspace, MemoryWorkspace
from geomind.tools.gemini.plants import load_plant, set_ranges, workspace_plant
from tests.fixtures.calls import call
from tests.fixtures.cases import (
    PLANTS,
    case_context,
    example_folder,
    example_plant,
    example_plant_files,
)
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
PLANT_FILES = [("hackathon_2026", name) for name in HACKATHON_PLANTS] + [
    ("shallow_district", "HeatingHeatPumpCoolingPlant")
]
every_example_plant = pytest.mark.parametrize(
    ("example", "plant"), PLANT_FILES, ids=[f"{example}/{plant}" for example, plant in PLANT_FILES]
)
CASED = [
    ("hackathon_2026", "HackathonPlant"),
    ("hackathon_2026", "HeatingHeatPumpCoolingPlant"),
    ("shallow_district", "HeatingHeatPumpCoolingPlant"),
]
cased_plants = pytest.mark.parametrize(
    ("example", "plant"), CASED, ids=[f"{example}/{plant}" for example, plant in CASED]
)


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


def plant_dict(example, plant):
    """Return an example plant file as the dict ``gm.Plant.to_dict(structure=True)`` writes."""
    return example_plant(example, plant).to_dict(structure=True)


async def read_with_and_without_case(example, plant):
    """Return ``read_plant`` of a stored design: without a case, then with the example's case."""
    session = StubSession()
    session.artifacts["design/x"] = plant_dict(example, plant)
    bare = await call(TOOLS.read_plant, {"design": "design/x"}, session)
    context = await case_context(example, session)
    cased = await call(TOOLS.read_plant, {"design": "design/x"}, session, problem=context.problem)
    return bare.output, cased.output


@pytest.fixture(scope="module")
def reads():
    """Return ``{(example, plant): (without case, with case)}``, read once for the module."""
    return {pair: asyncio.run(read_with_and_without_case(*pair)) for pair in CASED}


def test_build_plant_offers_a_short_schema_and_list_plants_gives_gemini_full_one(gm):
    """The offered ``plant`` is small; gemini's whole schema is one call away."""
    schema = gm.plants.schema()
    offered = TOOLS.build_plant.schema()["input_schema"]
    assert set(offered["properties"]["plant"]["properties"]) == set(schema["properties"])
    assert "$defs" not in offered
    assert len(str(offered)) < len(str(schema)) / 4
    full = asyncio.run(call(TOOLS.list_plants, {"with_schema": True}))
    assert full.output["schema"] == schema


async def test_list_plants_names_every_class_with_its_summary(gm):
    """The rows are gemini's names, in its order, with its summary."""
    result = await call(TOOLS.list_plants, {})
    rows = result.output["plants"]
    assert [row["name"] for row in rows] == gm.plants.names()
    assert rows[0] == {
        "name": rows[0]["name"],
        "summary": gm.plants.get(rows[0]["name"]).describe()["summary"],
    }
    assert "capabilities" not in result.output


@pytest.mark.parametrize("name", gemini.plants.names())
async def test_list_plants_gives_the_capabilities_and_roles_of_one_class(gm, name):
    """Every class's capabilities are reachable, and its roles are those it uses."""
    capabilities, roles = gm.plants.capabilities(), gm.plants.roles()
    output = (await call(TOOLS.list_plants, {"plant_class": name})).output
    assert output["capabilities"] == capabilities[name]
    assert output["roles"] == {role: roles[role] for role in capabilities[name]["roles"]}
    assert set(capabilities[name]) == {"roles", "schedulable", "ranges"}


async def test_list_plants_with_an_unknown_class_suggests_one():
    """A wrong class name is a result the model can act on."""
    result = await call(TOOLS.list_plants, {"plant_class": "HeatingPlan"})
    assert result.output["error"]["path"] == "plant_class"
    assert "HeatingPlant" in result.output["error"]["message"]


@cased_plants
def test_a_stored_design_reads_back_as_its_dict(reads, example, plant):
    """``read_plant`` of ``design/<name>`` is the plant dict that was stored."""
    without_case, with_case = reads[(example, plant)]
    assert without_case["plant"] == plant_dict(example, plant)
    assert with_case["plant"] == without_case["plant"]


@cased_plants
def test_without_a_case_the_issues_are_those_of_the_plant(gm, reads, example, plant):
    """No case in the state: gemini's ``plant.check()``, marked as checked against the plant."""
    without_case, _ = reads[(example, plant)]
    expected = [issue.problem() for issue in example_plant(example, plant).check()]
    assert without_case["checked_against"] == "plant"
    assert [(issue["path"], issue["code"]) for issue in without_case["issues"]] == [
        (item["path"], item["code"]) for item in expected
    ]


@pytest.mark.parametrize("example", ["hackathon_2026", "shallow_district"])
def test_the_case_fills_the_gradient_the_plant_alone_calls_missing(reads, example):
    """``d0.gradient`` is empty to take the case's; only the check against the case knows it."""
    without_case, with_case = reads[(example, "HeatingHeatPumpCoolingPlant")]
    assert "params.d0.gradient" in [issue["path"] for issue in without_case["issues"]]
    assert with_case["checked_against"] == "case"
    assert "params.d0.gradient" not in [issue["path"] for issue in with_case["issues"]]


def test_a_complete_plant_with_its_case_has_no_issues(reads):
    """The example's own plant and case agree: nothing is missing."""
    assert reads[("hackathon_2026", "HackathonPlant")][1]["issues"] == []


def test_ranges_are_shown_in_the_units_of_the_plant_file(reads):
    """A leaf with a unit shows ``{value, unit}`` in the file's unit; a count is a plain number."""
    ranges = reads[("hackathon_2026", "HeatingHeatPumpCoolingPlant")][0]["ranges"]
    assert ranges["size.doublets"] == {"min": 1, "max": 3}
    assert ranges["depth"] == {
        "min": {"value": 2000.0, "unit": "m"},
        "max": {"value": 3500.0, "unit": "m"},
    }
    assert ranges["heat_pump.capacity"]["min"] == {"value": 3.0, "unit": "MW"}
    assert ranges["d0.nominal_flow"]["max"] == {"value": 300.0, "unit": "m3/h"}


async def test_a_class_name_reads_as_a_plant_with_its_missing_values(gm):
    """A class has no values: the model reads what it must fill in."""
    result = await call(TOOLS.read_plant, {"plant_class": "HeatingPlant"})
    plant = gm.plants.get("HeatingPlant")
    assert not result.is_error
    assert result.output["plant"] == plant.to_dict(structure=True)
    assert result.output["checked_against"] == "plant"
    assert {issue["kind"] for issue in result.output["issues"]} == {"missing"}
    assert set(result.output["issues"][0]) == {"path", "code", "message", "kind", "units"}


@pytest.mark.parametrize("example", ["hackathon_2026", "shallow_district"])
async def test_a_class_read_with_a_case_lists_what_it_lacks_against_the_case(example):
    """A class has no values: gemini's check against the case lists them, and does not raise."""
    session = StubSession()
    context = await case_context(example, session)
    result = await call(
        TOOLS.read_plant,
        {"plant_class": "HeatingHeatPumpCoolingPlant"},
        session,
        problem=context.problem,
    )
    assert not result.is_error
    output = result.output
    assert output["checked_against"] == "case"
    paths = {issue["path"] for issue in output["issues"]}
    assert "params.heat_pump.mode" in paths


async def test_an_unknown_class_name_is_gemini_s_problem_with_suggestions():
    """A misspelt class gets gemini's close matches."""
    result = await call(TOOLS.read_plant, {"plant_class": "HeatingPlnt"})
    assert result.is_error
    assert result.output["error"]["suggestions"][0] == "HeatingPlant"


async def test_a_design_and_a_class_together_are_refused():
    """The two ways to name a plant exclude each other."""
    result = await call(TOOLS.read_plant, {"design": "design/x", "plant_class": "HeatingPlant"})
    assert result.output["error"]["path"] == "design"


@every_example_plant
async def test_build_plant_round_trips_each_example_plant(example, plant):
    """A valid plant file is stored as design/<name>, read back the same, with its issues."""
    data = plant_dict(example, plant)
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    assert built.output["design"] == "design/p"
    assert built.output["checked_against"] == "plant"
    assert session.artifacts["design/p"] == data
    read = await call(TOOLS.read_plant, {"design": "design/p"}, session)
    assert read.output["plant"] == data
    assert read.output["issues"] == built.output["issues"]


async def test_build_plant_checks_its_issues_against_the_case_of_the_state():
    """With a case in the state, the issues of the new design come from ``gm.check``."""
    session = StubSession()
    context = await case_context("hackathon_2026", session)
    data = plant_dict("hackathon_2026", "HeatingHeatPumpCoolingPlant")
    built = await call(
        TOOLS.build_plant, {"plant": data, "name": "p"}, session, problem=context.problem
    )
    assert built.output["checked_against"] == "case"
    assert "params.d0.gradient" not in [issue["path"] for issue in built.output["issues"]]


async def test_the_inputs_of_a_design_survive_storing():
    """The inputs a plant dict keeps are restored by ``from_dict``, with no bridge."""
    data = plant_dict("shallow_district", "HeatingHeatPumpCoolingPlant")
    assert data["inputs"] if "inputs" in data else data["params"]
    session = StubSession()
    await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    context = Context(session=session)
    assert load_plant(context, "design/p", "test").to_dict(structure=True) == data


async def test_a_wrong_parameter_name_is_gemini_s_error_with_its_path_and_suggestion():
    """The error keeps gemini's path and did-you-mean, and nothing is stored."""
    data = plant_dict("hackathon_2026", "HackathonPlant")
    params = data["params"]["d0"]
    params["depht"] = params.pop("depth")
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    error = built.output["error"]
    assert built.is_error
    assert error["path"] == "params.d0.depht"
    assert error["code"] == "unknown_name"
    assert error["suggestions"] == ["depth"]
    assert session.artifacts == {}


async def test_a_value_with_a_unit_string_is_refused_by_gemini():
    """``"2500 m"`` is not a quantity; the model is told to give ``{value, unit}``."""
    data = plant_dict("hackathon_2026", "HackathonPlant")
    data["params"]["d0"]["depth"] = "2500 m"
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": "p"}, session)
    assert built.output["error"]["path"] == "params.d0.depth"
    assert "{'value'" in built.output["error"]["message"]
    assert session.artifacts == {}


@pytest.mark.parametrize("name", ["a/b", "", "../x", "a b"])
async def test_a_design_name_must_be_one_safe_name(name):
    """The name becomes part of a store key, so it is checked before anything is stored."""
    data = plant_dict("shallow_district", "HeatingHeatPumpCoolingPlant")
    session = StubSession()
    built = await call(TOOLS.build_plant, {"plant": data, "name": name}, session)
    assert built.output["error"]["code"] == "invalid_input"
    assert built.output["error"]["path"] == "name"
    assert session.artifacts == {}


@pytest.fixture(scope="module")
def ranged():
    """Return the session of a ``set_ranges`` on a stored plant, and the tool's result."""
    session = StubSession()
    session.artifacts["design/base"] = plant_dict("hackathon_2026", "HeatingHeatPumpCoolingPlant")
    ranges = {
        "size.doublets": {"min": 2, "max": 4},
        "depth": {"min": {"value": 2.2, "unit": "km"}, "max": {"value": 3000, "unit": "m"}},
        "heat_pump.capacity": {"max": {"value": 20, "unit": "MW"}},
    }
    options = {"heat_pump.cop_model": ["carnot", "lorenz"]}
    tool_input = {"design": "design/base", "ranges": ranges, "options": options, "name": "wide"}
    result = asyncio.run(call(set_ranges, tool_input, session))
    return session, result


def test_set_ranges_stores_a_new_design_with_the_ranges(gm, ranged):
    """The stored design's ``plant.ranges`` and ``options`` are what was asked, in SI."""
    session, result = ranged
    assert result.output["design"] == "design/wide"
    plant = gm.Plant.from_dict(session.artifacts["design/wide"])
    assert plant.ranges["size.doublets"].max == 4
    assert plant.ranges["depth"].min == pytest.approx(2200.0)
    assert plant.ranges["depth"].max == pytest.approx(3000.0)
    assert plant.ranges["heat_pump.capacity"].max == pytest.approx(20e6)
    assert plant.options == {"heat_pump.cop_model": ("carnot", "lorenz")}


def test_set_ranges_shows_the_ranges_in_display_units(ranged):
    """The result reads as ``read_plant`` does: the range of each leaf in the file's unit."""
    ranges = ranged[1].output["ranges"]
    assert ranges["depth"]["min"] == {"value": 2200.0, "unit": "m"}
    assert ranges["heat_pump.capacity"]["max"] == {"value": 20.0, "unit": "MW"}
    assert ranged[1].output["options"] == {"heat_pump.cop_model": ["carnot", "lorenz"]}


def test_set_ranges_leaves_the_design_it_read_unchanged(gm, ranged):
    """The source design keeps its own ranges."""
    session, _ = ranged
    plant = gm.Plant.from_dict(session.artifacts["design/base"])
    assert plant.ranges["size.doublets"].max == 3


async def test_set_ranges_on_an_unknown_leaf_is_gemini_s_error_with_the_valid_paths():
    """Gemini names the path it refused and the paths that exist."""
    session = StubSession()
    session.artifacts["design/base"] = plant_dict("shallow_district", "HeatingHeatPumpCoolingPlant")
    bound = {"min": {"value": 1, "unit": "m"}}
    result = await call(
        set_ranges,
        {"design": "design/base", "ranges": {"deptth": bound}, "name": "x"},
        session,
    )
    error = result.output["error"]
    assert error["code"] == "unknown_name"
    assert error["path"] == "deptth"
    assert "size.doublets" in error["message"]
    assert "design/x" not in session.artifacts


async def test_set_ranges_refuses_a_bound_without_a_unit():
    """A bare number for a leaf with a unit is gemini's ``invalid_value`` with the leaf's path."""
    session = StubSession()
    session.artifacts["design/base"] = plant_dict("shallow_district", "HeatingHeatPumpCoolingPlant")
    result = await call(
        set_ranges,
        {"design": "design/base", "ranges": {"depth": {"min": 1000}}, "name": "x"},
        session,
    )
    assert result.output["error"]["code"] == "invalid_value"
    assert result.output["error"]["path"] == "depth.min"


async def test_set_ranges_of_an_unknown_design_is_unknown_name():
    """Only a stored design reference is read."""
    result = await call(set_ranges, {"design": "design/missing", "ranges": {}, "name": "x"})
    assert result.output["error"]["code"] == "unknown_name"


@pytest.mark.parametrize("design", ["design/missing", "result/r1"])
async def test_reading_an_unknown_design_reference_is_unknown_name(design):
    """Only a stored design reference reads back; ``result/`` is no design."""
    result = await call(TOOLS.read_plant, {"design": design})
    assert result.output["error"]["code"] == "unknown_name"


def example_workspace(example):
    """Return a memory workspace whose project ``p1`` holds every plant file of an example."""
    files = {
        name.removeprefix("plants/").removesuffix(".json"): json.loads(content)
        for name, content in example_plant_files(example).items()
    }
    return MemoryWorkspace(plants={"p1": files})


@every_example_plant
async def test_read_plant_by_project_plant_name_is_its_dict(example, plant):
    """A named project plant reads as the file's dict, the workspace left unchanged."""
    workspace = example_workspace(example)
    before = copy.deepcopy(workspace.plants("p1"))
    session = StubSession(workspace=workspace)
    result = await call(TOOLS.read_plant, {"project_plant": plant}, session, project="p1")
    assert result.output["plant"] == example_plant(example, plant).to_dict(structure=True)
    assert workspace.plants("p1") == before
    json.dumps(result.output)


async def test_read_plant_without_a_name_reads_the_one_plant_of_a_project():
    """A project with exactly one plant file needs no name."""
    workspace = example_workspace("shallow_district")
    result = await call(TOOLS.read_plant, {}, StubSession(workspace=workspace), project="p1")
    assert result.output["plant"] == plant_dict("shallow_district", PLANTS["shallow_district"])


async def test_read_plant_without_a_name_in_a_project_of_several_names_them():
    """Several files and no name: the error names the files and the three ways to choose."""
    session = StubSession(workspace=example_workspace("hackathon_2026"))
    result = await call(TOOLS.read_plant, {}, session, project="p1")
    error = result.output["error"]
    assert error["code"] == "unknown_name" and error["path"] == "project_plant"
    for text in ("HackathonPlant", "HeatingPlant", "plant class", "stored design"):
        assert text in error["message"]


async def test_an_unknown_project_plant_name_lists_the_known_ones():
    """The error names what the project holds."""
    session = StubSession(workspace=example_workspace("hackathon_2026"))
    result = await call(TOOLS.read_plant, {"project_plant": "Nope"}, session, project="p1")
    assert result.output["error"]["code"] == "unknown_name"
    assert "HeatingPlant" in result.output["error"]["message"]


async def test_list_plants_names_the_plant_files_of_the_project():
    """``project_plants`` is the sorted file names; empty without a project."""
    session = StubSession(workspace=example_workspace("hackathon_2026"))
    result = await call(TOOLS.list_plants, {}, session, project="p1")
    assert result.output["project_plants"] == sorted(HACKATHON_PLANTS)
    assert (await call(TOOLS.list_plants, {})).output["project_plants"] == []


async def test_project_plant_with_another_argument_is_refused():
    """The three ways to name a plant exclude each other."""
    session = StubSession(workspace=example_workspace("hackathon_2026"))
    arguments = {"project_plant": "HeatingPlant", "plant_class": "HeatingPlant"}
    result = await call(TOOLS.read_plant, arguments, session, project="p1")
    assert result.output["error"]["path"] == "design"


async def test_read_plant_without_a_project_says_so():
    """A run with no project cannot read the project's plant."""
    result = await call(TOOLS.read_plant, {})
    assert result.output["error"]["code"] == "not_allowed"


async def test_read_plant_of_a_project_without_a_plant_says_so():
    """A project with no plant is a result the model can act on."""
    session = StubSession(workspace=MemoryWorkspace())
    result = await call(TOOLS.read_plant, {}, session, project="p1")
    assert result.output["error"]["code"] == "unknown_name"


def test_a_file_workspace_project_with_several_plants_needs_a_name(tmp_path):
    """The file workspace of the hackathon layout gives each file by its stem."""
    shutil.copytree(example_folder("hackathon_2026"), tmp_path / "p1")
    context = Context(session=StubSession(workspace=FileWorkspace(tmp_path)), project="p1")
    with pytest.raises(ToolError, match="several plants"):
        workspace_plant(context, "read_plant")
    plant = workspace_plant(context, "read_plant", "HeatingPlant")
    assert plant.to_dict()["type"] == "HeatingPlant"
