"""The tools that judge a stored run, over gemini's example cases."""

import asyncio
import functools

import pytest

import geomind as gd
from tests.fixtures.calls import call
from tests.fixtures.cases import EXAMPLES, example_names
from tests.fixtures.stored_runs import stored_run, variant_run, warm_runs
from tests.fixtures.stubs import check_stub

TOOLS = gd.tools.gemini


ASSESSED = [
    *(("check_results", name, "base") for name in EXAMPLES),
    *(("compute_kpis", name, "base") for name in EXAMPLES),
    *(("estimate_costs", name, "base") for name in EXAMPLES),
    ("check_results", "hackathon_2026", "cooling_peak"),
    ("check_results", "hackathon_2026", "colder"),
    ("estimate_costs", "hackathon_2026", "cooling_peak"),
]
"""The tool calls on stored runs that the tests read; gemini's evaluation of a year is slow."""


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run the stored runs and the tool calls once, outside the timed test calls."""
    warm_runs()
    for tool, name, variant in ASSESSED:
        assessed(tool, name, variant)


@functools.cache
def assessed(tool, name, variant):
    """Return the output of a tool on the stored run of a variant, once per process."""
    return asyncio.run(assess(getattr(TOOLS, tool), name, variant)).output


async def test_the_module_test_says_when_it_comes():
    """It has its final signature and a phase."""
    await check_stub(TOOLS.test_module, {"path": "module.py"}, "execute", "S3")


async def assess_in(context, tool, result, **tool_input):
    """Call a tool on a stored run of a context; return its result."""
    request = {"reference": result, **tool_input}
    return await call(tool, request, context.session, problem=context.problem)


async def assess(tool, name, variant="base", **tool_input):
    """Call a tool on the stored run of a variant of an example; return its result."""
    context, _, result = variant_run(name, variant)
    return await assess_in(context, tool, result, **tool_input)


@example_names
def test_a_design_that_meets_its_case_is_feasible_by_gemini_s_verdict(name):
    """The verdict is gemini's: feasible, no reason, no failed row."""
    output = assessed("check_results", name, "base")
    assert output["feasible"] is True
    assert output["reasons"] == []
    assert output["failures"] == {"total": 0, "groups": []}
    assert output["requirements"]
    assert all(check["passed"] is not False for check in output["requirements"])
    assert output["metrics"]["failed_steps"] == 0


def test_check_results_shows_values_in_display_units():
    """Energy in MWh, money in MEUR, temperatures in degC; never bare SI."""
    output = assessed("check_results", "hackathon_2026", "base")
    metrics = output["metrics"]
    assert (metrics["heat_delivered"]["unit"], metrics["capex"]["unit"]) == ("MWh", "MEUR")
    units = {check["limit"]["unit"] for check in output["requirements"]}
    assert units >= {"m3/h", "degC"}


def test_a_cooling_peak_beyond_the_plant_fails_the_cold_delivered_and_its_supply():
    """At 15 MW the cooling is not all delivered and the grid gets warmer water than asked."""
    output = assessed("check_results", "hackathon_2026", "cooling_peak")
    assert output["feasible"] is False
    reasons = {reason["name"]: reason for reason in output["reasons"]}
    assert set(reasons) == {"cold_delivered", "cooling_supply_temperature"}
    assert {reason["kind"] for reason in reasons.values()} == {"requirement"}
    supply = reasons["cooling_supply_temperature"]
    assert (supply["role"], supply["quantity"]) == ("cooling_supply", "temperature")
    assert supply["value"]["value"] > supply["limit"]["value"]
    assert supply["limit"] == {"value": 20.0, "unit": "degC"}
    failed = [check for check in output["requirements"] if check["passed"] is False]
    assert [check["name"] for check in failed] == ["cold_delivered", "cooling_supply_temperature"]


def test_a_colder_reservoir_is_met_by_the_boiler_and_still_passes():
    """No requirement of the case limits the boiler, so gemini passes the 25 K/km variant.

    The cost shows the difference: the boiler gives over a hundred times the heat.
    """
    base = assessed("check_results", "hackathon_2026", "base")
    colder = assessed("check_results", "hackathon_2026", "colder")
    assert colder["feasible"] is True
    assert colder["metrics"]["boiler_heat"]["value"] > 100 * base["metrics"]["boiler_heat"]["value"]


@example_names
async def test_kpis_are_totals_and_report_metrics_in_display_units(name):
    """All of them without names, the ones asked for with them."""
    everything = assessed("compute_kpis", name, "base")
    assert {"heat_delivered", "heating_coverage", "cop", "peak_heat", "lcts"} <= set(everything)
    assert everything["heat_delivered"]["unit"] == "MWh"
    assert everything["peak_heat"]["unit"] == "MW"
    asked = (await assess(TOOLS.compute_kpis, name, names=["cop", "lcts"])).output
    assert asked == {"cop": everything["cop"], "lcts": everything["lcts"]}


async def test_an_unknown_kpi_is_unknown_name_with_a_suggestion():
    """The model reads the names that exist."""
    result = await assess(TOOLS.compute_kpis, "shallow_district", names=["peak_heats"])
    assert result.output["error"]["code"] == "unknown_name"
    assert "peak_heat" in result.output["error"]["message"]


@pytest.mark.parametrize("tool", [TOOLS.check_results, TOOLS.compute_kpis, TOOLS.estimate_costs])
async def test_an_unknown_result_is_unknown_name(tool):
    """Only a reference that simulate returned reads back."""
    result = await call(tool, {"reference": "result/missing"})
    assert result.output["error"]["code"] == "unknown_name"
    assert result.output["error"]["path"] == "reference"


async def test_costs_are_gemini_s_values_of_the_case_in_display_units():
    """Capex, opex, the levelised costs, NPV, payback, CO2 and the annualised cost."""
    import gemini as gm

    context, _, result = variant_run("hackathon_2026", "base")
    output = assessed("estimate_costs", "hackathon_2026", "base")
    plant, case, _ = gd.tools.gemini.stored.load_run(context, result, "test")
    assert output["capex"]["value"] == pytest.approx(
        gm.evaluate.capex(plant, case).to("MEUR").value
    )
    assert {key: item["unit"] for key, item in output.items()} == {
        "capex": "MEUR",
        "opex": "MEUR/yr",
        "annualised_cost": "MEUR/yr",
        "lcoh": "EUR/MWh",
        "lcoc": "EUR/MWh",
        "lcts": "EUR/MWh",
        "npv": "MEUR",
        "payback": "yr",
        "co2": "kt",
    }


async def test_a_cost_whose_assumption_is_missing_is_gemini_s_error_beside_the_others():
    """The shallow economics gives no heat revenue: NPV and payback say so, capex is still there."""
    output = assessed("estimate_costs", "shallow_district", "base")
    assert output["capex"]["unit"] == "MEUR" and output["lcts"]["unit"] == "EUR/MWh"
    for name in ("npv", "payback"):
        assert output[name]["error"]["code"] == "missing_assumption"
        assert output[name]["error"]["path"] == "economics.revenue.heat"


def test_costs_follow_the_cooling_demand():
    """The same design costs more to run when it must cool more."""
    base = assessed("estimate_costs", "hackathon_2026", "base")
    peak = assessed("estimate_costs", "hackathon_2026", "cooling_peak")
    assert peak["opex"]["value"] > base["opex"]["value"]


async def test_a_case_without_economics_gives_gemini_s_missing_assumption():
    """The model reads the path to ask the user for; nothing is filled in."""
    context, _, result = await stored_run("shallow_district")
    identifier = result.removeprefix("result/")
    ran_on = dict(context.session.load_artifact(f"{identifier}.case"))
    del ran_on["economics"]
    await context.session.save_artifact(f"{identifier}.case", ran_on)
    output = (await assess_in(context, TOOLS.estimate_costs, result)).output
    assert output["error"]["code"] == "missing_assumption"
    assert output["error"]["path"].startswith("economics")
