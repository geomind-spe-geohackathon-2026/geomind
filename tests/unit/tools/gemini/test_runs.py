"""The tools that read the case's demand and run a plant on the case, on both example cases."""

import pytest

import geomind as gd
from geomind.context import ProblemState
from geomind.tools.gemini.case import save_profile, set_case
from geomind.tools.gemini.stored import save_design
from tests.fixtures.calls import call
from tests.fixtures.cases import (
    SHALLOW_PEAK_HEATING,
    case_context,
    example_case,
    example_names,
    example_plant,
)

TOOLS = gd.tools.gemini
HEATING_PEAK_MW = {"hackathon_2026": 30.0, "shallow_district": SHALLOW_PEAK_HEATING / 1e6}
WINDOWS = {
    "hackathon_2026": ("2027-01-01", "2027-01-10", 10),
    "shallow_district": ("2026-01-12", "2026-01-13T23:00:00", 48),
}
CHANGES = {
    "hackathon_2026": {"boiler": {"capacity": {"value": 20, "unit": "MW"}}},
    "shallow_district": {"heat_pump": {"capacity": {"value": 1.0, "unit": "MW"}}},
}
ALLOWED_UNITS = {"MWh", "MEUR", "MEUR/yr", "EUR/MWh", "kt", "-", None}


@pytest.fixture(scope="module", autouse=True)
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


async def designed(name):
    """Return ``(context, session, problem)`` of an example with its plant stored as design/p."""
    context = await case_context(name)
    await save_design(context, "p", example_plant(name))
    return context.session, context.problem


async def simulated(name, **arguments):
    """Return the result of ``simulate`` on an example's stored design."""
    session, problem = await designed(name)
    return await call(TOOLS.simulate, {"design": "design/p", **arguments}, session, problem=problem)


def case_steps(name):
    """Return the number of steps of an example case's time."""
    import gemini as gm

    return len(gm.Case.from_dict(*example_case(name)).time.index)


@example_names
async def test_simulate_runs_the_stored_design_on_the_case(name):
    """The run covers the case's time, no step fails and the reference reads back."""
    session, problem = await designed(name)
    result = await call(TOOLS.simulate, {"design": "design/p"}, session, problem=problem)
    summary = result.output["summary"]
    assert result.output["reference"].startswith("result/")
    assert summary["steps"] == case_steps(name) and summary["failed_steps"] == 0
    assert summary["plant"] == "design/p"
    assert summary["case_time"]["start"] and summary["case_time"]["step"]["unit"] in ("d", "h")
    assert summary["failures"] == []


@example_names
async def test_the_summary_is_in_readable_units(name):
    """Energy in MWh, money in MEUR or EUR/MWh, mass in kt: never joules or bare SI."""
    summary = (await simulated(name)).output["summary"]
    units = {item["unit"] for item in summary["report"].values() if isinstance(item, dict)}
    assert units <= ALLOWED_UNITS
    assert summary["report"]["heat_delivered"]["unit"] == "MWh"
    assert summary["report"]["heat_delivered"]["value"] > 0
    assert summary["coverage"]["heating_coverage"]["value"] == pytest.approx(1.0)


@example_names
async def test_a_run_is_reproducible(name):
    """The same plant, case and options give the same reference; another option another one."""
    session, problem = await designed(name)
    arguments = {"design": "design/p"}
    first = await call(TOOLS.simulate, arguments, session, problem=problem)
    again = await call(TOOLS.simulate, arguments, session, problem=problem)
    start, end, _ = WINDOWS[name]
    windowed = await call(TOOLS.simulate, {**arguments, "start": start}, session, problem=problem)
    assert first.output["reference"] == again.output["reference"]
    assert windowed.output["reference"] != first.output["reference"]


@example_names
async def test_a_window_cuts_the_run(name):
    """``start`` and ``end`` are inclusive and the summary names the window that ran."""
    start, end, steps = WINDOWS[name]
    summary = (await simulated(name, start=start, end=end)).output["summary"]
    assert summary["steps"] == steps
    assert summary["window"]["start"].startswith(start[:10])


@example_names
async def test_a_window_outside_the_case_is_an_input_error(name):
    """Nothing to run is told, with the case's time."""
    result = await simulated(name, start="1999-01-01", end="1999-01-02")
    assert result.is_error and "case's time" in result.output["error"]["message"]


@example_names
async def test_changes_apply_for_this_run_only(name):
    """A change gives another run and leaves the stored design as it was."""
    session, problem = await designed(name)
    before = session.load_artifact("design/p")
    plain = await call(TOOLS.simulate, {"design": "design/p"}, session, problem=problem)
    changed = await call(
        TOOLS.simulate, {"design": "design/p", "changes": CHANGES[name]}, session, problem=problem
    )
    assert changed.is_error is False
    assert changed.output["reference"] != plain.output["reference"]
    assert session.load_artifact("design/p") == before


@example_names
async def test_a_bare_number_for_a_dimensional_parameter_is_refused(name):
    """Units are explicit: a number for a power says to give ``{value, unit}``."""
    bare = {next(iter(CHANGES[name])): {"capacity": 20.0}}
    result = await simulated(name, changes=bare)
    assert result.is_error and "unit" in result.output["error"]["message"]


async def test_a_state_without_a_case_says_what_to_call():
    """No case: the model is told to call set_case or ask_user."""
    from geomind.engine import Context
    from tests.fixtures.sessions import StubSession

    context = Context(session=StubSession())
    await save_design(context, "p", example_plant("shallow_district"))
    result = await call(TOOLS.simulate, {"design": "design/p"}, context.session)
    assert result.is_error
    assert "set_case" in result.output["error"]["message"]
    assert "ask_user" in result.output["error"]["message"]


@example_names
async def test_read_profile_gives_the_peak_in_megawatts(name):
    """The case's heating demand reads in MW with its times."""
    session, problem = await designed(name)
    result = await call(TOOLS.read_profile, {"service": "heating"}, session, problem=problem)
    output = result.output
    assert output["unit"] == "MW"
    assert len(output["time"]) == len(output["value"]) == case_steps(name)
    assert max(output["value"]) == pytest.approx(HEATING_PEAK_MW[name])


@example_names
async def test_read_profile_takes_a_window(name):
    """Both ends are inclusive."""
    session, problem = await designed(name)
    start, end, steps = WINDOWS[name]
    arguments = {"service": "heating", "start": start, "end": end}
    result = await call(TOOLS.read_profile, arguments, session, problem=problem)
    assert len(result.output["value"]) == steps


async def test_a_service_the_case_lacks_lists_what_exists():
    """An unknown service is an unknown_name with the services of the demand."""
    session, problem = await designed("shallow_district")
    result = await call(TOOLS.read_profile, {"service": "steam"}, session, problem=problem)
    assert result.output["error"]["code"] == "unknown_name"
    assert "heating" in result.output["error"]["message"]


@example_names
async def test_list_profiles_names_the_services_of_the_demand(name):
    """Each service with its temperatures in degC, window and peak in MW."""
    session, problem = await designed(name)
    result = await call(TOOLS.list_profiles, {}, session, problem=problem)
    rows = {row["service"]: row for row in result.output}
    assert set(rows) == {"heating", "cooling"}
    assert rows["heating"]["supply_temperature"]["unit"] == "degC"
    assert rows["heating"]["peak"]["unit"] == "MW"
    assert rows["heating"]["peak"]["value"] == pytest.approx(HEATING_PEAK_MW[name])


async def test_without_a_case_the_profiles_say_what_to_call():
    """No case, no demand: the same tool error as a run."""
    from geomind.engine import Context
    from tests.fixtures.sessions import StubSession

    result = await call(TOOLS.list_profiles, {}, StubSession())
    assert result.is_error and "set_case" in result.output["error"]["message"]
    assert Context  # imported for the type of the session only


def evolved(session):
    """Return the problem state after the last recorded change of a session."""
    return ProblemState(version=1, case=session.changes[-1][0]["value"])


def profile_call(service, values):
    """Return the input of save_profile for 30 daily values in MW from 2027-01-01."""
    return {
        "name": service,
        "values": values,
        "unit": "MW",
        "start": "2027-01-01",
        "step": {"value": 1, "unit": "d"},
        "service": service,
    }


async def test_a_30_day_user_profile_simulates():
    """set_case cuts the case to 30 days, save_profile adds the user's demand, simulate runs."""
    context = await case_context("hackathon_2026")
    session = context.session
    await save_design(context, "p", example_plant("hackathon_2026"))
    original = example_case("hackathon_2026")[0]
    limits = [c for c in original["constraints"] if c.get("over") != "duration"]
    time = {"start": "2027-01-01", "end": "2027-01-31", "step": {"value": 1, "unit": "d"}}
    cut = {"changes": {"time": time, "demand": None, "constraints": limits}}
    await call(set_case, cut, session, problem=context.problem)
    heating = [18 + 8 * (day % 7) / 6 for day in range(30)]
    for service, values in (("heating", heating), ("cooling", [5.0] * 30)):
        saved = await call(
            save_profile, profile_call(service, values), session, problem=evolved(session)
        )
        assert saved.is_error is False, saved.output
    temperatures = {
        service: {
            key: original["demand"][service][key]
            for key in ("supply_temperature", "return_temperature")
        }
        for service in ("heating", "cooling")
    }
    await call(set_case, {"changes": {"demand": temperatures}}, session, problem=evolved(session))
    problem = evolved(session)
    ran = await call(TOOLS.simulate, {"design": "design/p"}, session, problem=problem)
    assert ran.is_error is False, ran.output
    summary = ran.output["summary"]
    assert (summary["steps"], summary["failures"]) == (30, [])
    assert summary["report"]["heat_delivered"]["value"] >= sum(heating) * 24 * (1 - 1e-6)
    read = await call(TOOLS.read_profile, {"service": "heating"}, session, problem=problem)
    assert max(read.output["value"]) == pytest.approx(max(heating))
