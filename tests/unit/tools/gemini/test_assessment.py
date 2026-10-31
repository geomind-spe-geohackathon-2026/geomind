"""The tools that judge a design, over stored runs of gemini's hackathon example."""

import asyncio

import pytest

import geomind as gd
from tests.fixtures.calls import call
from tests.fixtures.hackathon import PRICES, hackathon_spec
from tests.fixtures.sessions import StubSession
from tests.fixtures.stubs import check_stub

TOOLS = gd.tools.gemini


@pytest.mark.parametrize(
    ("tool", "tool_input", "effect", "phase"),
    [
        (TOOLS.test_module, {"path": "module.py"}, "execute", "S3"),
        (
            TOOLS.optimize,
            {"design": "design/a", "variables": {}, "objective": "lcoh"},
            "compute",
            "S4",
        ),
        (
            TOOLS.sample_uncertainty,
            {"design": "design/a", "distributions": {}, "samples": 10, "metrics": ["lcoh"]},
            "compute",
            "S4",
        ),
    ],
)
async def test_the_stubs_say_when_they_come(tool, tool_input, effect, phase):
    """Each has its final signature and a phase."""
    await check_stub(tool, tool_input, effect, phase)


@pytest.fixture(scope="module")
def gm():
    """Return gemini; importing it takes more than one test call's budget."""
    import gemini

    return gemini


async def run_in(session, gm, start, end):
    """Store the hackathon design, simulate it in a window and return the result reference."""
    await call(TOOLS.build_plant, {"plant": hackathon_spec(gm), "name": "hackathon"}, session)
    window = {"design": "design/hackathon", "start": start, "end": end}
    return (await call(TOOLS.simulate, window, session)).output["reference"]


@pytest.fixture(scope="module")
def stored(gm):
    """Return a session holding two runs of the hackathon design, and their references.

    ``spring`` (late March) supplies heat below 100 degC; ``winter`` (January) meets the brief.
    """
    session = StubSession()
    spring = asyncio.run(run_in(session, gm, "2027-03-20", "2027-03-31"))
    winter = asyncio.run(run_in(session, gm, "2027-01-01", "2027-01-10"))
    return session, {"spring": spring, "winter": winter}


async def test_check_results_names_a_broken_hard_limit_and_its_domain(stored):
    """In late March the example supplies heat below 100 degC: a surface failure."""
    session, references = stored
    result = await call(TOOLS.check_results, {"reference": references["spring"]}, session)
    output = result.output
    assert output["passed"] is False
    assert {"name": "heat_users.supply_in.temperature", "domain": "surface"} in output["failures"]
    assert set(output) == {"passed", "checks", "failures", "not_assessed"}


async def test_check_results_passes_a_run_that_meets_the_brief(stored):
    """In January the example meets every hard limit."""
    session, references = stored
    result = await call(TOOLS.check_results, {"reference": references["winter"]}, session)
    assert result.output["passed"] is True


async def test_compute_kpis_returns_gemini_s_kpis_and_totals(gm, stored):
    """``gm.kpi.compute`` and ``gm.kpi.totals``, each a Value; ``names`` picks some."""
    session, references = stored
    reference = references["winter"]
    every = (await call(TOOLS.compute_kpis, {"reference": reference}, session)).output
    picked = {"reference": reference, "names": ["peak_heat", "heat_delivered"]}
    some = await call(TOOLS.compute_kpis, picked, session)
    assert set(gm.kpi.names()) <= set(every) and "heat_delivered" in every
    assert some.output == {
        "peak_heat": every["peak_heat"],
        "heat_delivered": every["heat_delivered"],
    }
    assert every["peak_heat"]["unit"] == "W"


async def test_an_unknown_kpi_is_unknown_name_with_a_suggestion(stored):
    """The model reads the names that exist."""
    session, references = stored
    wrong = {"reference": references["winter"], "names": ["peak_heats"]}
    result = await call(TOOLS.compute_kpis, wrong, session)
    assert result.output["error"]["code"] == "unknown_name"
    assert "peak_heat" in result.output["error"]["message"]


@pytest.mark.parametrize("tool", [TOOLS.check_results, TOOLS.compute_kpis, TOOLS.estimate_costs])
async def test_an_unknown_result_is_unknown_name(gm, tool):
    """Only a reference that simulate returned reads back."""
    result = await call(tool, {"reference": "result/missing"})
    assert result.output["error"]["code"] == "unknown_name"
    assert result.output["error"]["path"] == "reference"


def gemini_costs(gm, session, reference, values):
    """Return gemini's own economics of a stored run, called directly."""
    from geomind.engine import Context
    from geomind.tools.gemini.assessment import stored_run

    plant, results = stored_run(Context(session=session), reference, "test")
    assumptions = gm.economics.Assumptions(**values)
    economics = gm.economics
    return {
        "capex": economics.capex(plant, assumptions, on_error="record"),
        "opex": economics.opex(plant, results, assumptions, on_error="record"),
        "lcoh": economics.lcoh(plant, results, assumptions=assumptions, on_error="record"),
        "lcoc": economics.lcoc(plant, results, assumptions=assumptions, on_error="record"),
        "npv": economics.npv(plant, results, assumptions=assumptions, on_error="record"),
        "co2": economics.co2(plant, results, assumptions, on_error="record"),
    }


@pytest.fixture(scope="module")
def costed(gm, stored):
    """Return ``estimate_costs`` of a May run (heat and cold) under three sets of assumptions.

    Each comes with gemini's own economics of the same run, called directly; the tool calls are
    made here because each takes most of one test call's budget.
    """
    session, _ = stored
    may = asyncio.run(run_in(session, gm, "2027-05-01", "2027-05-10"))
    sets = {
        "share": {**PRICES, "heat_cost_share": 0.8},
        "prices": PRICES,
        "energy": {**PRICES, "heat_cost_share": "energy"},
        "none": {},
    }
    outputs = {
        name: asyncio.run(
            call(TOOLS.estimate_costs, {"reference": may, "assumptions": values}, session)
        ).output
        for name, values in sets.items()
    }
    expected = {
        "share": gemini_costs(gm, session, may, sets["share"]),
        "whole": gemini_costs(gm, session, may, {**PRICES, "heat_cost_share": 1.0}),
    }
    return outputs, expected


def test_estimate_costs_returns_gemini_s_values_and_the_assumptions(gm, costed):
    """Capex, opex, LCOH, LCOC, NPV and CO2 are gemini's, with every assumption used."""
    outputs, expected = costed
    output = outputs["share"]
    assert {name: output[name] for name in expected["share"]} == expected["share"]
    values = {**PRICES, "heat_cost_share": 0.8}
    assert output["assumptions"] == gm.economics.Assumptions(**values).model_dump(mode="json")
    assert output["lcoh"]["value"] is not None and output["lcoc"]["value"] is not None


def test_lcts_is_the_annualised_system_cost_over_heat_and_cold(costed):
    """LCTS = annualised total cost / (annual heat + annual cold), all from gemini's parts."""
    outputs, expected = costed
    lcts = outputs["prices"]["lcts"]
    whole = expected["whole"]
    heat, cold = whole["lcoh"]["energy"]["value"], whole["lcoc"]["energy"]["value"]
    annual = whole["lcoh"]["value"] * heat
    assert cold > 0
    assert lcts["value"] == pytest.approx(annual / (heat + cold), rel=1e-12)
    assert lcts["unit"] == "EUR/J"
    assert lcts["annualised_cost"] == {
        "value": pytest.approx(annual, rel=1e-12),
        "unit": "EUR/year",
    }
    assert 0 < lcts["value"] < whole["lcoh"]["value"]


def test_a_missing_assumption_is_a_null_value_with_gemini_s_reason(costed):
    """Without a discount rate the levelised costs have no value, and say why."""
    outputs, _ = costed
    assert outputs["none"]["lcoh"]["value"] is None
    assert "discount_rate" in outputs["none"]["lcoh"]["reason"]
    assert outputs["none"]["lcts"]["value"] is None


def test_the_heat_cost_share_may_follow_the_delivered_energy(costed):
    """``"energy"`` splits the cost by the heat and cold delivered, read from gm.kpi.totals."""
    outputs, expected = costed
    whole = expected["whole"]
    heat, cold = whole["lcoh"]["energy"]["value"], whole["lcoc"]["energy"]["value"]
    share = outputs["energy"]["assumptions"]["heat_cost_share"]
    assert share == pytest.approx(heat / (heat + cold), rel=1e-9)


@pytest.mark.parametrize(
    ("assumptions", "code", "path"),
    [
        ({"discount_rates": 0.05}, "unknown_name", "assumptions.discount_rates"),
        ({"discount_rate": "five"}, "invalid_input", "assumptions.discount_rate"),
    ],
)
async def test_a_wrong_assumption_is_a_result_the_model_can_fix(stored, assumptions, code, path):
    """An unknown name or a wrong value names the assumption."""
    session, references = stored
    request = {"reference": references["winter"], "assumptions": assumptions}
    result = await call(TOOLS.estimate_costs, request, session)
    assert (result.output["error"]["code"], result.output["error"]["path"]) == (code, path)
