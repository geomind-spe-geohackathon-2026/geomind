"""The tools that read the case's demand and run a plant on the case, on both example cases."""

import asyncio
import functools
import json

import pytest

import geomind as gd
from geomind.context import ProblemState
from geomind.context.state import apply_changes
from geomind.tools.gemini.case import save_profile, set_case
from geomind.tools.gemini.stored import save_design
from tests.fixtures.calls import call
from tests.fixtures.cases import (
    EXAMPLES,
    SHALLOW_PEAK_HEATING,
    case_context,
    example_case,
    example_names,
    example_plant,
)
from tests.fixtures.stored_runs import scaled_column
from tests.fixtures.stored_runs import simulated as year_run

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
GASES = {
    "sour": {"CH4": {"value": 0.75}, "CO2": {"value": 0.2}, "H2S": {"value": 0.05}},
    "sweet": {"CH4": {"value": 0.8}, "CO2": {"value": 0.2}},
}


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run each example's year and its windows once, outside the timed test calls."""
    for name in EXAMPLES:
        year_run(name)
        windowed(name)
    peak_run("hackathon_2026")
    for gas in GASES:
        gas_run(gas)


@functools.cache
def peak_run(name):
    """Return the result of ``simulate`` on a case whose cooling demand is scaled to fail it."""

    async def run():
        context = await case_context(name)
        file = context.problem.case["demand"]["cooling"]["power"]["file"]
        content = context.session.load_artifact(f"case/{file}")
        scaled = scaled_column(
            content, example_case(name)[0]["demand"]["cooling"]["power"]["column"], 1.5
        )
        await context.session.save_artifact(f"case/{file}", scaled)
        await save_design(context, "p", example_plant(name))
        return await call(
            TOOLS.simulate, {"design": "design/p"}, context.session, problem=context.problem
        )

    return asyncio.run(run())


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
def test_simulate_runs_the_stored_design_on_the_case(name):
    """The run covers the case's time, no step fails and the reference reads back."""
    result = year_run(name)[1]
    summary = result.output["summary"]
    assert result.output["reference"].startswith("result/")
    assert summary["steps"] == case_steps(name) and summary["failed_steps"] == 0
    assert summary["plant"] == "design/p"
    assert summary["case_time"]["start"] and summary["case_time"]["step"]["unit"] in ("d", "h")
    assert summary["failures"] == []
    assert summary["verdict"]["feasible"] is True and summary["unmet"] == []
    assert "constraints" not in summary and "violated" not in summary


@example_names
def test_the_summary_is_in_readable_units(name):
    """Energy in MWh, money in MEUR or EUR/MWh, mass in kt: never joules or bare SI."""
    summary = year_run(name)[1].output["summary"]
    units = {item["unit"] for item in summary["report"].values() if isinstance(item, dict)}
    assert units <= ALLOWED_UNITS
    assert summary["report"]["heat_delivered"]["unit"] == "MWh"
    assert summary["report"]["heat_delivered"]["value"] > 0
    assert summary["coverage"]["heating_coverage"]["value"] == pytest.approx(1.0)


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


async def window_runs(name):
    """Return the stored design before, and four runs of it: plain, again, longer and changed."""
    session, problem = await designed(name)
    before = session.load_artifact("design/p")
    start, end, _ = WINDOWS[name]
    arguments = {"design": "design/p", "start": start, "end": start}
    variants = {
        "plain": arguments,
        "again": arguments,
        "longer": {**arguments, "end": end},
        "changed": {**arguments, "changes": CHANGES[name]},
    }
    runs = {
        key: await call(TOOLS.simulate, value, session, problem=problem)
        for key, value in variants.items()
    }
    return session, before, runs


@functools.cache
def windowed(name):
    """Return ``window_runs`` of an example, once per process, outside the timed test calls."""
    return asyncio.run(window_runs(name))


@example_names
def test_a_run_is_reproducible(name):
    """The same plant, case and options give the same reference."""
    runs = windowed(name)[2]
    assert runs["plain"].output["reference"] == runs["again"].output["reference"]


@example_names
def test_another_option_is_another_run(name):
    """Another window of the same plant and case gives another reference."""
    runs = windowed(name)[2]
    assert runs["longer"].output["reference"] != runs["plain"].output["reference"]


@example_names
def test_changes_apply_for_this_run_only(name):
    """A change gives another run and leaves the stored design as it was."""
    session, before, runs = windowed(name)
    assert runs["changed"].is_error is False
    assert runs["changed"].output["reference"] != runs["plain"].output["reference"]
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
    assert output["summary"]["peak"]["value"] == pytest.approx(HEATING_PEAK_MW[name])


def test_a_profile_s_summary_is_computed_by_code_not_by_the_agent():
    """#71: engineers read a year of values again and again to find its peak and energy."""
    import pandas as pd

    from geomind.tools.gemini.runs import profile_summary

    times = pd.date_range("2027-01-01", periods=3, freq="D", tz="UTC")
    summary = profile_summary(times, [2.0, 5.0, 1.0])
    assert summary["peak"] == {"value": 5.0, "time": "2027-01-02T00:00:00+00:00"}
    assert summary["minimum"]["value"] == 1.0 and summary["mean"] == pytest.approx(8 / 3)
    assert summary["energy"] == {"value": pytest.approx(8.0 * 24), "unit": "MWh"}
    assert profile_summary(times[:0], []) is None


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
    power = example_case(name)[0]["demand"]["heating"]["power"]
    assert rows["heating"]["power"] == power
    assert rows["heating"]["supply_temperature"]["unit"] == "degC"
    assert rows["heating"]["peak"]["unit"] == "MW"
    assert rows["heating"]["peak"]["value"] == pytest.approx(HEATING_PEAK_MW[name])


async def test_list_profiles_lists_a_service_with_no_return_temperature():
    """The end-to-end case left both return temperatures open: the row says None (#125)."""
    context = await case_context("hackathon_2026")
    for service in ("heating", "cooling"):
        del context.problem.case["demand"][service]["return_temperature"]
    result = await call(TOOLS.list_profiles, {}, context.session, problem=context.problem)
    assert not result.is_error, result.output
    rows = {row["service"]: row for row in result.output}
    assert rows["heating"]["return_temperature"] is None
    assert rows["heating"]["supply_temperature"]["unit"] == "degC"


async def test_without_a_case_the_profiles_say_what_to_call():
    """No case, no demand: the same tool error as a run."""
    from tests.fixtures.sessions import StubSession

    result = await call(TOOLS.list_profiles, {}, StubSession())
    assert result.is_error and "set_case" in result.output["error"]["message"]


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
    """set_case cuts the case to 30 days, save_profile points the demand at the user's values."""
    context = await case_context("hackathon_2026")
    session = context.session
    await save_design(context, "p", example_plant("hackathon_2026"))
    original = example_case("hackathon_2026")[0]
    durations = {c["name"]: None for c in original["requirements"] if c.get("over") == "duration"}
    time = {"start": "2027-01-01", "end": "2027-01-31", "step": {"value": 1, "unit": "d"}}
    cut = {"changes": {"time": time}, "requirements": durations}
    first = await call(set_case, cut, session, problem=context.problem)
    assert first.is_error is False, first.output
    heating = [18 + 8 * (day % 7) / 6 for day in range(30)]
    for service, values in (("heating", heating), ("cooling", [5.0] * 30)):
        saved = await call(
            save_profile, profile_call(service, values), session, problem=evolved(session)
        )
        assert saved.is_error is False, saved.output
    problem = evolved(session)
    ran = await call(TOOLS.simulate, {"design": "design/p"}, session, problem=problem)
    assert ran.is_error is False, ran.output
    summary = ran.output["summary"]
    assert (summary["steps"], summary["failures"]) == (30, [])
    assert summary["report"]["heat_delivered"]["value"] >= sum(heating) * 24 * (1 - 1e-6)
    read = await call(TOOLS.read_profile, {"service": "heating"}, session, problem=problem)
    assert max(read.output["value"]) == pytest.approx(max(heating))
    listed = await call(TOOLS.list_profiles, {}, session, problem=problem)
    power = {row["service"]: row["power"] for row in listed.output}["heating"]
    assert power == {"unit": "MW", "file": "data/heating.csv", "column": "heating"}


def test_an_unmet_requirement_is_listed_by_name():
    """A cooling peak the plant cannot serve is a verdict, not an error: the unmet ones show."""
    summary = peak_run("hackathon_2026").output["summary"]
    assert summary["verdict"]["feasible"] is False and summary["report"]["passed"] is False
    assert {"cold_delivered", "cooling_supply_temperature"} <= {
        item["name"] for item in summary["unmet"]
    }
    assert all(item["passed"] is False for item in summary["unmet"])


@functools.cache
def gas_run(gas):
    """Return ``simulate`` over one day of the hackathon plant, its brine's gas set by set_case."""

    async def run():
        session, problem = await designed("hackathon_2026")
        changes = {"site": {"fluid": {"dissolved_gas": GASES[gas]}}}
        result = await call(set_case, {"changes": changes}, session, problem=problem)
        assert result.is_error is False, result.output
        problem = apply_changes(problem, session.changes[-1])
        start = WINDOWS["hackathon_2026"][0]
        arguments = {"design": "design/p", "start": start, "end": start}
        return await call(TOOLS.simulate, arguments, session, problem=problem)

    return asyncio.run(run())


def test_a_brine_gas_with_h2s_simulates_and_its_h2s_forms_no_co2():
    """B3 (gemini 0.6.4): H2S in the dissolved gas failed the plant's build; it runs now.

    With 5 mol% H2S in place of as much CH4, the gas burnt (boiler, flare) emits less CO2.
    """
    sour, sweet = gas_run("sour"), gas_run("sweet")
    assert sour.is_error is False, sour.output
    summary = sour.output["summary"]
    assert summary["failed_steps"] == 0 and summary["failures"] == []
    assert summary["report"]["co2"]["value"] < sweet.output["summary"]["report"]["co2"]["value"]


@example_names
async def test_a_missing_case_file_is_named(name):
    """A case whose series is not in the run says which file is missing."""
    context = await case_context(name)
    file = example_case(name)[0]["demand"]["heating"]["power"]["file"]
    context.session.artifacts.pop(f"case/{file}")
    await save_design(context, "p", example_plant(name))
    result = await call(
        TOOLS.simulate, {"design": "design/p"}, context.session, problem=context.problem
    )
    assert result.is_error and file in result.output["error"]["message"]


async def test_a_plant_that_gemini_s_check_rejects_comes_back_with_the_issue():
    """Equipment without a cost in the economics is gemini's issue with its path, nothing runs."""
    context = await case_context("hackathon_2026")
    economics = json.loads(context.session.load_artifact("case/economics.json"))
    del economics["capex"]["drilling"]
    await context.session.save_artifact("case/economics.json", json.dumps(economics).encode())
    await save_design(context, "p", example_plant("hackathon_2026"))
    result = await call(
        TOOLS.simulate, {"design": "design/p"}, context.session, problem=context.problem
    )
    error = result.output["error"]
    assert result.is_error and error["path"] == "economics.capex.drilling"
    assert error["code"] == "case_incomplete"


@example_names
async def test_a_profile_shows_the_case_window_and_its_file_s_own_rows(name):
    """#60: a year ending at an exclusive 31 Dec read as a file of 364 values, and a day was cut.

    Beside the series: the case's window, its end exclusive, and the data file's own rows.
    """
    session, problem = await designed(name)
    output = (
        await call(TOOLS.read_profile, {"service": "heating"}, session, problem=problem)
    ).output
    assert output["case_time"]["end_is"] == "exclusive"
    assert output["case_time"]["steps"] == case_steps(name)
    extent = output["file"]
    assert extent is None or (extent["rows"] >= 1 and extent["first"] <= extent["last"])


async def test_an_esp_curve_failure_names_the_flows_where_the_curve_is_negative():
    """E2E-15: 450 steps failed on one flow's negative head, and the lead invented a new curve.

    The failure of an ESP outside its curves gives the flows from zero to its ``maximum_flow``
    where the curve's head or power is below zero, so the curve's source can be checked.
    """
    session, problem = await designed("shallow_district")
    curve = {"head_coefficients": [-3000.0, 1.0, 0, 0, 0, 0], "stage_count": 1}
    curve["power_coefficients"] = [10.0, 0.01, 0, 0, 0, 0]
    window = {"start": "2026-01-12", "end": "2026-01-12T05:00:00"}
    ran = await call(
        TOOLS.simulate,
        {"design": "design/p", "changes": {"d0.esp": curve}, **window},
        session,
        problem=problem,
    )
    failure = ran.output["summary"]["failures"][0]
    assert (failure["path"], failure["code"]) == ("d0.esp", "out_of_range")
    found = failure["curve"]
    assert found["unit"] == "m3/s" and found["flows"] == [0.0, 1.0]
    assert found["negative_power"] == []
    ((start, end),) = found["negative_head"]
    zero = 3000 / 543439.65
    assert start == 0.0 and zero - found["resolution"] <= end < zero
    assert "negative head at flows 0 to" in failure["message"]
