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
from tests.fixtures import ROOT
from tests.fixtures.calls import call
from tests.fixtures.cases import (
    PLANTS,
    case_context,
    example_case,
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


def same_plant(shown, stored):
    """Tell whether a shown plant file builds the plant of a stored dict, whatever its units."""
    def built(data):
        return gemini.Plant.from_dict(data).to_dict(structure=True, units="si")

    return built(shown) == built(stored)


def plant_dict(example, plant):
    """Return an example plant file as the dict ``gm.Plant.to_dict(structure=True)`` writes."""
    return example_plant(example, plant).to_dict(structure=True)


def shown_dict(example, plant):
    """Return an example plant file as ``read_plant`` shows it: in gemini's display units (30).

    A class plant shows its own file, its class, size and given values (QA-247).
    """
    from geomind.tools.gemini.plants import editable_dict

    return editable_dict(example_plant(example, plant), units="display")


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
    assert same_plant(without_case["plant"], plant_dict(example, plant))
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
    assert result.output["plant"] == plant.to_dict()
    assert "d0" in result.output["modules"]
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
    assert same_plant(read.output["plant"], data)
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
    assert result.output["plant"] == shown_dict(example, plant)
    assert workspace.plants("p1") == before
    json.dumps(result.output)


async def test_read_plant_without_a_name_reads_the_one_plant_of_a_project():
    """A project with exactly one plant file needs no name."""
    workspace = example_workspace("shallow_district")
    result = await call(TOOLS.read_plant, {}, StubSession(workspace=workspace), project="p1")
    assert result.output["plant"] == shown_dict("shallow_district", PLANTS["shallow_district"])


async def test_read_plant_gives_the_values_in_display_units():
    """#110: the explainer wrote 30000000.0 W as 30 MW itself; gemini 0.6.3 gives MW (30)."""
    import gemini as gm

    workspace = example_workspace("hackathon_2026")
    session = StubSession(workspace=workspace)
    arguments = {"project_plant": "HackathonPlant"}
    shown = (await call(TOOLS.read_plant, arguments, session, project="p1")).output["plant"]
    assert shown["params"]["heat_pump"]["capacity"] == {
        "value": 15.0,
        "unit": "MW",
        "range": {"min": 3.0, "max": 30.0},
    }
    plant = example_plant("hackathon_2026", "HackathonPlant")
    assert gm.Plant.from_dict(shown).to_dict(units="si") == plant.to_dict(units="si")


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


async def test_a_plant_is_built_step_by_step_with_small_patches(gm):
    """A class plant starts small; a patch fills one module's values and only the rest is listed."""
    session = StubSession()
    start = {
        "name": "p0",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant"},
    }
    first = (await call(TOOLS.build_plant, start, session)).output
    missing = {issue["path"] for issue in first["issues"]}
    assert "params.d0.drainage_radius" in missing
    patch = {"params": {"d0": {"drainage_radius": {"value": 500, "unit": "m"}}}}
    step = {"design": "design/p0", "changes": patch, "name": "p1"}
    second = (await call(TOOLS.patch_plant, step, session)).output
    assert second["design"] == "design/p1"
    still = {issue["path"] for issue in second["issues"]}
    assert "params.d0.drainage_radius" not in still and still < missing
    assert second["missing"] == len(still)


async def test_read_plant_output_builds_back_and_names_its_stored_design(gm):
    """QA-247, QA-221: a project plant reads as a file build_plant takes, with its reference."""
    workspace = example_workspace("hackathon_2026")
    session = StubSession(workspace=workspace)
    plant = "HeatingHeatPumpCoolingPlant"
    read = await call(TOOLS.read_plant, {"project_plant": plant}, session, project="p1")
    assert read.output["design"] == f"design/{plant}"
    assert "never type it again" in read.output["use"]
    built = await call(TOOLS.build_plant, {"plant": read.output["plant"], "name": "copy"}, session)
    assert not built.is_error


async def test_a_class_plant_keeps_its_type_and_size_through_a_patch(gm):
    """QA-260: 2 doublets stay 2 after a value patch; a size patch resizes the class plant."""
    session = StubSession()
    start = {
        "name": "two",
        "plant": {
            "format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant",
            "size": {"doublets": {"value": 2}},
        },
    }
    assert not (await call(TOOLS.build_plant, start, session)).is_error
    patch = {"params": {"d0": {"drainage_radius": {"value": 500, "unit": "m"}}}}
    step = {"design": "design/two", "changes": patch, "name": "two_b"}
    assert not (await call(TOOLS.patch_plant, step, session)).is_error
    stored = session.artifacts["design/two_b"]
    assert stored["type"] == "HeatingPlant"
    assert stored["size"]["doublets"]["value"] == 2
    assert "d1" in stored["modules"]
    resize = {"design": "design/two_b", "changes": {"size": {"doublets": {"value": 3}}},
              "name": "three"}
    assert not (await call(TOOLS.patch_plant, resize, session)).is_error
    assert "d2" in session.artifacts["design/three"]["modules"]


async def test_a_class_extended_with_from_class_keeps_the_size_it_is_given(gm):
    """QA-260: build_plant with from_class makes the class's modules at the given size."""
    session = StubSession()
    start = {
        "name": "ext",
        "from_class": "HeatingPlant",
        "plant": {"format": 1, "kind": "plant", "name": "p", "size": {"doublets": {"value": 2}}},
    }
    built = await call(TOOLS.build_plant, start, session)
    assert not built.is_error
    assert "d1" in session.artifacts["design/ext"]["modules"]


async def test_a_version_alias_is_no_new_design_name(gm):
    """QA-221: design/v<N> is a project plant version; a new design may not take that name."""
    start = {
        "name": "v1",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant"},
    }
    result = await call(TOOLS.build_plant, start, StubSession())
    assert result.is_error
    assert "pass design/v1" in result.output["error"]["message"]


async def test_a_patch_gemini_refuses_stores_nothing(gm):
    """A wrong key comes back as gemini's error; the earlier design stays as it was."""
    session = StubSession()
    start = {
        "name": "p0",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant"},
    }
    await call(TOOLS.build_plant, start, session)
    step = {
        "design": "design/p0",
        "changes": {"params": {"d0": {"nope": {"value": 1}}}},
        "name": "p1",
    }
    result = await call(TOOLS.patch_plant, step, session)
    assert result.is_error and "design/p1" not in session.artifacts


async def test_designs_patched_side_by_side_are_merged_on_their_base(gm):
    """Two engineers patch different modules from one base; the merge holds both changes."""
    session = StubSession()
    start = {
        "name": "base",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant"},
    }
    await call(TOOLS.build_plant, start, session)
    radius = {"params": {"d0": {"drainage_radius": {"value": 500, "unit": "m"}}}}
    roughness = {"params": {"d0": {"roughness": {"value": 0.0001, "unit": "m"}}}}
    for name, patch in (("a", radius), ("b", roughness)):
        step = {"design": "design/base", "changes": patch, "name": name}
        await call(TOOLS.patch_plant, step, session)
    merged = {"base": "design/base", "designs": ["design/a", "design/b"], "name": "m"}
    output = (await call(TOOLS.merge_designs, merged, session)).output
    params = session.artifacts["design/m"]["params"]["d0"]
    assert output["design"] == "design/m"
    assert params["drainage_radius"]["value"] == 500 and params["roughness"]["value"] == 0.0001
    still = {issue["path"] for issue in output["issues"]}
    assert "params.d0.drainage_radius" not in still and "params.d0.roughness" not in still


async def test_two_designs_setting_one_value_differently_are_a_conflict(gm):
    """Nothing is stored and the error names the path and both designs."""
    session = StubSession()
    start = {
        "name": "base",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant"},
    }
    await call(TOOLS.build_plant, start, session)
    for name, radius in (("a", 500), ("b", 600)):
        patch = {"params": {"d0": {"drainage_radius": {"value": radius, "unit": "m"}}}}
        step = {"design": "design/base", "changes": patch, "name": name}
        await call(TOOLS.patch_plant, step, session)
    merged = {"base": "design/base", "designs": ["design/a", "design/b"], "name": "m"}
    result = await call(TOOLS.merge_designs, merged, session)
    assert result.is_error and "design/m" not in session.artifacts
    assert "params.d0.drainage_radius.value" in result.output["error"]["message"]
    assert "design/a" in result.output["error"]["message"]


async def union_of(session, kinds):
    """Build one design per plant class and join them with ``union_designs``."""
    for name, kind in kinds.items():
        plant = {"format": 1, "kind": "plant", "name": name, "type": kind}
        await call(TOOLS.build_plant, {"name": name, "plant": plant}, session)
    designs = [f"design/{name}" for name in kinds]
    return await call(TOOLS.union_designs, {"designs": designs, "name": "u"}, session)


async def test_whole_alternatives_are_joined_by_gemini_s_union(gm):
    """By ``gm.plants.union`` (gemini 0.6.2): a superstructure whose structures give each design."""
    session = StubSession()
    kinds = {"heat": "HeatingPlant", "both": "HeatingHeatPumpCoolingPlant"}
    result = await union_of(session, kinds)
    output = result.output
    assert not result.is_error, output
    assert output["design"] == "design/u" and "design/u" in session.artifacts
    assert set(output["structures"]) == {"design/heat", "design/both"}
    assert output["structures"]["design/both"]["heat_pump"] is True
    assert output["structures"]["design/heat"]["heat_pump"] is False
    assert "heat_pump" in session.artifacts["design/u"]["optional"]
    assert output["missing"] == len(output["issues"])
    json.dumps(output)


async def test_designs_gemini_cannot_join_are_its_error_and_nothing_is_stored(gm):
    """A module the union would make optional with no bypass is gemini's ``invalid_design``."""
    session = StubSession()
    result = await union_of(session, {"heat": "HeatingPlant", "cool": "HeatingCoolingPlant"})
    assert result.is_error and result.output["error"]["code"] == "invalid_design"
    assert "design/u" not in session.artifacts


def test_a_merge_patch_of_two_plant_files_holds_only_what_differs():
    """Changed leaves, added keys and removed keys; a list is one value."""
    from geomind.tools.gemini.plants import leaf_changes, plant_difference

    base = {"a": {"b": 1, "c": 2}, "d": [1], "e": 3}
    other = {"a": {"b": 1, "c": 5}, "d": [1, 2], "f": 4}
    patch = plant_difference(base, other)
    assert patch == {"a": {"c": 5}, "d": [1, 2], "e": None, "f": 4}
    assert leaf_changes(patch) == {"a.c": 5, "d": [1, 2], "e": None, "f": 4}


async def test_a_stream_mismatch_reaches_the_agent_with_both_ends_and_suggestions(gm):
    """A connection gemini 0.6 refuses, electricity into a brine inlet, names both ends."""
    plant = json.loads((ROOT / "evals/projects/hackathon/plants/HackathonPlant.json").read_text())
    wrong = next(item for item in plant["connections"] if item["target"] == "degasser.fluid_in")
    wrong["source"] = "grid.power_out"
    result = await call(TOOLS.build_plant, {"plant": plant, "name": "wrong"}, StubSession())
    error = result.output["error"]
    assert result.is_error and error["code"] == "stream_mismatch"
    assert "grid.power_out" in error["message"] and "degasser.fluid_in" in error["message"]
    assert error["suggestions"] and len(json.dumps(error)) < 1500


async def test_a_format_given_as_text_is_read_as_its_number(gm):
    """#57: the design lead sent ``"format": "1"`` four times and was told the header was old."""
    plant = {"format": "1", "kind": "plant", "name": "p", "type": "HeatingPlant"}
    result = await call(TOOLS.build_plant, {"plant": plant, "name": "p0"}, StubSession())
    assert not result.is_error and result.output["design"] == "design/p0"


async def test_a_superstructure_goes_through_build_plant_as_gemini_stores_it(gm):
    """``optional`` and ``choices`` are keys of the plant file; they are kept when stored."""
    plant = json.loads((ROOT / "evals/projects/hackathon/plants/HackathonPlant.json").read_text())
    plant["optional"] = ["boiler"]
    session = StubSession()
    result = await call(TOOLS.build_plant, {"plant": plant, "name": "super"}, session)
    assert not result.is_error, result.output
    assert session.artifacts["design/super"]["optional"] == ["boiler"]


async def test_an_engineer_s_parameters_written_in_modules_are_patched(gm):
    """The run's reservoir engineer wrote ``modules.d0``: it is ``params.d0``, stored by gemini."""
    from geomind.context import ProblemState

    class Reservoir:
        discipline = "reservoir"

    session = StubSession()
    session.agent = Reservoir()
    start = {
        "name": "p0",
        "plant": {"format": 1, "kind": "plant", "name": "p", "type": "HeatingPlant"},
    }
    await call(TOOLS.build_plant, start, session)
    patch = {"modules": {"d0": {"drainage_radius": {"value": 500, "unit": "m"}}}}
    step = {"design": "design/p0", "changes": patch, "name": "p1"}
    result = await call(TOOLS.patch_plant, step, session, problem=ProblemState())
    assert not result.is_error, result.output
    assert session.artifacts["design/p1"]["params"]["d0"]["drainage_radius"]["value"] == 500


STORAGE_MODULES = {"thermal_storage": {"type": "ThermalStorage"}}
STORAGE_CONNECTIONS = [
    {"source": "heat_pump.sink_out", "target": "thermal_storage.charge_in"},
    {"source": "thermal_storage.charge_out", "target": "peak_boiler.fluid_in"},
    {"source": "heating_return_pipe.fluid_out", "target": "thermal_storage.discharge_in"},
    {"source": "thermal_storage.discharge_out", "target": "heat_exchanger.cold_in"},
    {"source": "atmosphere.air_out", "target": "thermal_storage.air_in"},
    {"source": "thermal_storage.loss_out", "target": "atmosphere.heat_in"},
]
"""What the process engineer's free plant that built (seq 3504, run 4ca94d6e) adds to its class."""
STORAGE_OPTIONAL = ["heat_pump", "compression_chiller", "peak_boiler", "thermal_storage"]


async def test_a_class_plant_with_a_module_its_class_lacks_names_from_class():
    """#143: ``optional[3]: module = 'thermal_storage'; expected a module of the plant``."""
    data = plant_dict("hackathon_2026", "HeatingHeatPumpCoolingPlant")
    data = {**data, "optional": STORAGE_OPTIONAL}
    built = await call(TOOLS.build_plant, {"plant": data, "name": "p"}, StubSession())
    error = built.output["error"]
    assert built.is_error and error["path"] == "from_class"
    assert "expected a module of the plant" in error["message"]
    assert "thermal_storage is no module of the class HeatingHeatPumpCoolingPlant" in (
        error["message"]
    )
    assert "from_class='HeatingHeatPumpCoolingPlant'" in error["message"]


async def test_from_class_adds_an_optional_module_with_its_connections(gm):
    """The run's added module, connections and optional build on the class; nothing retyped."""
    session = StubSession()
    plant = {
        "format": 1,
        "kind": "plant",
        "name": "geothermal_hc_2027",
        "modules": STORAGE_MODULES,
        "connections": STORAGE_CONNECTIONS,
        "optional": STORAGE_OPTIONAL,
    }
    tool_input = {"plant": plant, "name": "p", "from_class": "HeatingHeatPumpCoolingPlant"}
    built = await call(TOOLS.build_plant, tool_input, session)
    assert built.output["design"] == "design/p", built.output
    stored = session.artifacts["design/p"]
    assert "type" not in stored and stored["optional"] == STORAGE_OPTIONAL
    connections = stored["connections"]
    assert all(item in connections for item in STORAGE_CONNECTIONS)
    replaced = {"source": "heat_pump.sink_out", "target": "peak_boiler.fluid_in"}
    assert replaced not in connections
    kept = {"source": "atmosphere.air_out", "target": "compression_cooler.air_in"}
    assert kept in connections


COOLING_BRANCH = [
    "compression_chiller",
    "compression_cooler",
    "cooling_consumer",
    "cooling_supply_pipe",
    "cooling_return_pipe",
]
"""The cooling branch of ``HeatingHeatPumpCoolingPlant``: a whole branch can be off in 0.6.2."""


async def test_a_superstructure_turns_the_peak_boiler_and_the_cooling_branch_on_or_off(gm):
    """The peak boiler and the cooling branch are choices on or off: four structures (0.6.2).

    The peak boiler goes with its gas makeup and gas grid; a module's bypass is the plant's
    ``bypass``.
    """
    session = StubSession()
    plant = {
        "format": 1,
        "kind": "plant",
        "name": "super",
        "choices": {
            "boiler": {"on": ["peak_boiler", "gas_makeup", "gas_grid"], "off": []},
            "cooling": {"on": COOLING_BRANCH, "off": []},
        },
        "bypass": {"gas_makeup": {"gas_in": "excess_out"}},
    }
    tool_input = {"plant": plant, "name": "s", "from_class": "HeatingHeatPumpCoolingPlant"}
    built = await call(TOOLS.build_plant, tool_input, session)
    assert built.output["design"] == "design/s", built.output
    stored = session.artifacts["design/s"]
    assert stored["choices"] == plant["choices"] and stored["bypass"] == plant["bypass"]
    structures = gm.Plant.from_dict(stored).structures()
    assert {"boiler": "off", "cooling": "off"} in structures and len(structures) == 4


async def test_from_class_with_an_unconnected_added_port_is_gemini_s_error():
    """A port of the added module left out is named by gemini; an unknown class is refused."""
    plant = {"format": 1, "kind": "plant", "name": "x", "modules": STORAGE_MODULES}
    tool_input = {"plant": plant, "name": "p", "from_class": "HeatingHeatPumpCoolingPlant"}
    built = await call(TOOLS.build_plant, tool_input, StubSession())
    assert built.output["error"]["code"] == "unconnected_port"
    assert built.output["error"]["path"].startswith("thermal_storage.")
    unknown = await call(
        TOOLS.build_plant, {**tool_input, "from_class": "HeatingPlnt"}, StubSession()
    )
    assert unknown.output["error"]["path"] == "from_class"
    assert "did you mean 'HeatingPlant'" in unknown.output["error"]["message"]


def test_a_doublet_without_one_design_value_names_it_alone():
    """Requests 11 and 28: gemini 0.6.3 names ``d0.well_diameter``, not every value it derives.

    The design prompts say so; before, the engineers copied the case's reservoir values by hand.
    """
    import gemini as gm

    from tests.fixtures import ROOT

    data, files = example_case("hackathon_2026")
    case = gm.Case.from_dict(data, files=files)
    folder = ROOT / "tests" / "fixtures" / "gemini_examples" / "hackathon_2026" / "plants_brief"
    plant = json.loads((folder / "HeatingHeatPumpCoolingPlant.json").read_text())
    del plant["params"]["d0"]["well_diameter"]
    issues = [issue.problem()["path"] for issue in gm.check(gm.Plant.from_dict(plant), case)]
    assert issues == ["params.d0.well_diameter"]


def hand_set_pump(plant):
    """Return a HackathonPlant file whose pump the well engineer sets by hand (E2E-13).

    Without the doublet's pump design values gemini derives no pump; the engineer gives the ESP,
    the well below it and the riser above it, but no ``riser.esp_depth``.
    """
    plant = copy.deepcopy(plant)
    d0 = plant["params"]["d0"]
    for name in ("pump_efficiency", "nominal_wellhead_pressure"):
        del d0[name]
    d0["esp"] |= {
        "stage_count": {"value": 1},
        "head_coefficients": {"value": [300.0, 0, 0, 0, 0, 0]},
        "power_coefficients": {"value": [200000.0, 0, 0, 0, 0, 0]},
        "setting_depth": {"value": 1000, "unit": "m"},
    }
    d0["well"] |= {"segment": {"value": "below_esp"}, "esp_depth": {"value": 1000, "unit": "m"}}
    d0["riser"] |= {"segment": {"value": "above_esp"}}
    return plant


async def patched_issues(plant, changes):
    """Return ``patch_plant``'s output for ``changes`` on a stored ``plant`` with its case."""
    session = StubSession()
    session.artifacts["design/x"] = plant
    context = await case_context("hackathon_2026", session)
    step = {"design": "design/x", "changes": changes, "name": "y"}
    return (await call(TOOLS.patch_plant, step, session, problem=context.problem)).output


async def stored_issues(plant):
    """Return ``read_plant``'s output for a stored ``plant`` with its case: its issues unpatched."""
    session = StubSession()
    session.artifacts["design/x"] = plant
    context = await case_context("hackathon_2026", session)
    step = {"design": "design/x"}
    return (await call(TOOLS.read_plant, step, session, problem=context.problem)).output


async def test_patch_plant_refuses_a_patch_that_changes_nothing(reads):
    """QA-145: an empty or same-value patch stores no new version; it is refused ``no_change``."""
    plant = plant_dict("hackathon_2026", "HackathonPlant")
    for changes in ({}, {"params": {"control": plant["params"]["control"]}}):
        error = (await patched_issues(plant, changes))["error"]
        assert error["code"] == "no_change"
        assert error["path"] == "changes"


async def test_patch_plant_names_the_schedule_rules_simulate_needs(gm):
    """E2E-13: gemini's check passes a plant without ``control``; its schedule then refuses it.

    Both rules are named at once, each with the values gemini's schedule implements.
    """
    plant = plant_dict("hackathon_2026", "HackathonPlant")
    output = await patched_issues(plant, {"params": {"control": None}})
    issues = {issue["path"]: issue for issue in output["issues"]}
    assert set(issues) == {"params.control.dispatch", "params.control.outages"}
    assert output["missing"] == 2
    assert issues["params.control.outages"]["code"] == "missing_value"
    assert issues["params.control.outages"]["suggestions"] == ["lowest_demand"]
    assert issues["params.control.dispatch"]["suggestions"] == ["least_cost"]


async def test_patch_plant_names_a_split_riser_without_its_pump_depth(gm):
    """E2E-13: the riser above a hand-set pump needs ``esp_depth``; only a run found it before."""
    plant = hand_set_pump(plant_dict("hackathon_2026", "HackathonPlant"))
    output = await stored_issues(plant)
    assert [issue["path"] for issue in output["issues"]] == ["params.d0.riser.esp_depth"]
    assert output["issues"][0]["code"] in ("invalid_design", "missing_value")
    assert len(output["issues"]) == 1
    depth = {"params": {"d0": {"riser": {"esp_depth": {"value": 1000, "unit": "m"}}}}}
    assert (await patched_issues(plant, depth))["missing"] == 0


async def test_a_plant_ready_for_its_case_still_has_no_issues_after_the_run_check(reads):
    """The run check finds nothing on the example's own plant: a ready plant stays ready."""
    output = await stored_issues(plant_dict("hackathon_2026", "HackathonPlant"))
    assert output["issues"] == []


def test_plant_writes_are_checked_before_the_approval():
    """IMP-018: build_plant, patch_plant and merge_designs have a precheck that stores nothing."""
    from geomind.tools.gemini.plants import build_plant, merge_designs, patch_plant
    from geomind.tools.gemini.stored import DRY_DESIGNS

    assert all(callable(item.precheck) for item in (build_plant, patch_plant, merge_designs))
    assert DRY_DESIGNS.get() is False
