"""The tools that judge a design, over stored runs of gemini's hackathon example."""

import asyncio

import pytest

import geomind as gd
from tests.fixtures.calls import call
from tests.fixtures.hackathon import hackathon_spec
from tests.fixtures.sessions import StubSession
from tests.fixtures.stubs import check_stub

TOOLS = gd.tools.gemini


@pytest.mark.parametrize(
    ("tool", "tool_input", "effect", "phase"),
    [
        (TOOLS.estimate_costs, {"reference": "result/a"}, "compute", "S3"),
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


@pytest.mark.parametrize("tool", [TOOLS.check_results, TOOLS.compute_kpis])
async def test_an_unknown_result_is_unknown_name(gm, tool):
    """Only a reference that simulate returned reads back."""
    result = await call(tool, {"reference": "result/missing"})
    assert result.output["error"]["code"] == "unknown_name"
    assert result.output["error"]["path"] == "reference"
