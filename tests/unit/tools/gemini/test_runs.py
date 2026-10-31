"""The tools that read profiles and run a plant, against real gemini profiles and plants."""

import pytest

import geomind as gd
from geomind.stores import MemoryWorkspace
from geomind.tools.gemini.brief import SCHEDULE_RULES
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
    """Return the spec of gemini's example doublet heat plant."""
    return gm.plants.example("DoubletHeatPlant").to_dict()


HACKATHON_INPUTS = {
    "heat_pump": {"temperature_setpoint": "100 degC"},
    "boiler": {"temperature_setpoint": "100 degC"},
    "chiller": {"temperature_setpoint": "20 degC"},
    "cool_users": {"indoor_temperature": "26 degC", "indoor_relative_humidity": 0.5},
    "chiller_cooler": {"temperature_setpoint": "15 degC", "flow": "800 kg/s"},
    "air": {"temperature": "10 degC"},
    "desander": {"sand_concentration": "20 mg/l"},
    "dosing": {"dose": "10 ppm"},
}
"""The inputs of gemini's ``examples/cases/hackathon.py``, as a design stores them."""


@pytest.fixture(scope="module")
def hackathon(gm):
    """Return the spec of gemini's hackathon plant with its inputs kept in ``boundary``."""
    return {
        **gm.plants.example("HackathonPlant").to_dict(),
        "boundary": {"": {"inputs": HACKATHON_INPUTS}},
    }


@pytest.fixture(scope="module")
def hackathon_run(gm):
    """Return gemini's own run of the hackathon example on both demand profiles."""
    import pandas as pd

    plant = gm.plants.example("HackathonPlant")
    plant.set_inputs(
        {
            f"{path}.{name}": value
            for path, values in HACKATHON_INPUTS.items()
            for name, value in values.items()
        }
    )
    demand = pd.concat([gm.profiles.get(name) for name in gm.profiles.names()], axis=1)
    return gm.simulate(plant, gm.schedule(plant, demand, SCHEDULE_RULES), on_error="record")


async def stored_hackathon(session, hackathon):
    """Store the hackathon design in a session and return its reference."""
    built = await call(TOOLS.build_plant, {"plant": hackathon, "name": "hackathon"}, session)
    return built.output["design"]


def project_session(gm, spec):
    """Return a session whose project ``p1`` holds the example doublet."""
    return StubSession(workspace=MemoryWorkspace(plants={"p1": gm.plants.from_dict(spec)}))


def own_run(gm, spec, changes=None):
    """Return gemini's own run of the example doublet on the heating demand."""
    plant = gm.plants.from_dict(spec)
    for path, params in (changes or {}).items():
        plant.set_params(path, params)
    plan = gm.schedule(plant, gm.profiles.get("heating_demand"), SCHEDULE_RULES)
    return gm.simulate(plant, plan, on_error="record")


async def test_list_profiles_names_each_profile_with_its_unit_and_window(gm):
    """One row per gemini profile, from the profile itself."""
    result = await call(TOOLS.list_profiles, {})
    frame = gm.profiles.get("heating_demand")
    assert [row["name"] for row in result.output] == gm.profiles.names()
    assert result.output[0] == {
        "name": "heating_demand",
        "quantity": "power",
        "unit": "W",
        "start": frame.index[0].isoformat(),
        "end": frame.index[-1].isoformat(),
    }


async def test_read_profile_is_a_series_value_of_the_whole_year(gm):
    """Every day, in gemini's unit, with its time."""
    result = await call(TOOLS.read_profile, {"name": "cooling_demand"})
    frame = gm.profiles.get("cooling_demand")
    assert result.output["unit"] == "W"
    assert result.output["value"] == frame["cooling_demand"].tolist()
    assert result.output["time"][0] == "2027-01-01T00:00:00+00:00"
    assert len(result.output["time"]) == 365


async def test_read_profile_takes_a_window_with_both_ends(gm):
    """``start`` and ``end`` are ISO 8601 times, both included."""
    window = {"name": "heating_demand", "start": "2027-01-27", "end": "2027-01-29"}
    result = await call(TOOLS.read_profile, window)
    assert len(result.output["value"]) == 3
    assert max(result.output["value"]) == pytest.approx(30e6)


async def test_an_unknown_profile_is_gemini_s_problem(gm):
    """The model reads gemini's ``unknown_name``."""
    result = await call(TOOLS.read_profile, {"name": "heat"})
    assert result.output["error"]["code"] == "unknown_name"


@pytest.mark.parametrize("field", ["start", "end"])
async def test_a_time_that_is_not_iso_8601_is_invalid_input(gm, field):
    """A wrong time names its field."""
    result = await call(TOOLS.read_profile, {"name": "heating_demand", field: "28 Jan"})
    assert result.output["error"] == {
        "path": field,
        "code": "invalid_input",
        "message": result.output["error"]["message"],
        "suggestions": [],
    }


async def test_simulate_stores_what_read_result_reads_with_gemini_s_numbers(
    hackathon, hackathon_run
):
    """The stored series are gemini's own run, value for value, inputs of the design applied."""
    session = StubSession()
    design = await stored_hackathon(session, hackathon)
    ran = await call(TOOLS.simulate, {"design": design}, session)
    expected = hackathon_run.to_dict()["series"]
    read = await call(
        TOOLS.read_result,
        {"reference": ran.output["reference"], "path": "d0.reservoir", "field": "liquid_flow"},
        session,
    )
    assert ran.output["summary"]["failed_steps"] == 0
    assert session.artifacts[ran.output["reference"]] == {
        path: {
            field: {"unit": item["unit"], "values": item["value"]} for field, item in fields.items()
        }
        for path, fields in expected.items()
    }
    assert read.output == {
        "value": expected["d0.reservoir"]["liquid_flow"]["value"],
        "unit": "m3/s",
    }


async def test_failed_days_are_gemini_s_problems_in_the_summary(gm, spec):
    """The example doublet cannot run the demand year; each day is one of gemini's problems."""
    session = project_session(gm, spec)
    ran = await call(TOOLS.simulate, {"profile": "heating_demand"}, session, project="p1")
    assert ran.output["summary"]["failed_steps"] == 365
    assert ran.output["summary"]["errors"][0]["code"] == "out_of_range"
    assert session.artifacts[ran.output["reference"]] == {}


async def test_simulate_keeps_the_results_and_the_plant_beside_the_result(gm, spec):
    """``Results.to_bytes()`` and the plant are stored, for the checks and costs of S3."""
    session = project_session(gm, spec)
    ran = await call(TOOLS.simulate, {"profile": "heating_demand"}, session, project="p1")
    identifier = ran.output["reference"].removeprefix("result/")
    results = gm.Results.from_bytes(session.artifacts[f"{identifier}.results"])
    assert results.to_dict()["series"] == own_run(gm, spec).to_dict()["series"]
    assert session.artifacts[f"{identifier}.plant"] == spec


async def test_simulate_summarises_the_window_failures_and_totals(gm, spec):
    """The summary says how many days ran and failed, with gemini's problems and totals."""
    session = project_session(gm, spec)
    ran = await call(TOOLS.simulate, {"profile": "heating_demand"}, session, project="p1")
    summary = ran.output["summary"]
    own = own_run(gm, spec)
    assert summary["steps"] == 365
    assert summary["start"] == "2027-01-01T00:00:00+00:00"
    assert summary["failed_steps"] == len(own.errors())
    assert summary["errors"] == own.errors()[:5]
    assert summary["totals"] == gm.kpi.totals(gm.plants.from_dict(spec), own)


async def test_the_same_run_gets_the_same_reference(gm, spec):
    """The reference follows the inputs, so a replay finds the same result."""
    session = project_session(gm, spec)
    first = await call(TOOLS.simulate, {"profile": "heating_demand"}, session, project="p1")
    second = await call(TOOLS.simulate, {"profile": "heating_demand"}, session, project="p1")
    assert first.output["reference"] == second.output["reference"]


async def test_changes_apply_for_this_run_only(gm, hackathon):
    """``changes`` are ``set_params`` by module path; the stored design is not changed."""
    session = StubSession()
    design = await stored_hackathon(session, hackathon)
    changes = {"hx": {"thermal_conductance": "500000 W/K"}}
    week = {"design": design, "start": "2027-01-01", "end": "2027-01-07"}
    base = await call(TOOLS.simulate, week, session)
    changed = await call(TOOLS.simulate, {**week, "changes": changes}, session)
    identifier = changed.output["reference"].removeprefix("result/")
    plant = gm.plants.from_dict(session.artifacts[f"{identifier}.plant"])
    assert plant.params_at("hx")["thermal_conductance"] == 500000
    assert changed.output["reference"] != base.output["reference"]
    assert session.artifacts[design] == hackathon


async def test_simulate_without_a_project_or_design_says_so(gm):
    """There is no plant to run."""
    ran = await call(TOOLS.simulate, {"profile": "heating_demand"})
    assert ran.output["error"]["code"] == "not_allowed"


async def test_a_design_gemini_cannot_schedule_is_gemini_s_problem(gm):
    """A plant without the setpoints a schedule needs is a result, never an internal error."""
    session = StubSession()
    plant = gm.plants.example("HackathonPlant").to_dict()
    await call(TOOLS.build_plant, {"plant": plant, "name": "hackathon"}, session)
    ran = await call(TOOLS.simulate, {"design": "design/hackathon"}, session)
    assert ran.output["error"]["code"] == "invalid_design"
