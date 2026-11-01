"""The tools over a stored run's results and the project's documents."""

import pytest

import geomind as gd
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.stores import MemoryWorkspace
from geomind.tools import search_documents
from tests.fixtures.calls import call
from tests.fixtures.cases import EXAMPLES, example_names
from tests.fixtures.sessions import StubSession
from tests.fixtures.stored_runs import simulated

TOOLS = gd.tools.gemini
MODULES = {"hackathon_2026": "boiler", "shallow_district": "heat_pump"}


@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Run each example's year once, outside the timed test calls."""
    for name in EXAMPLES:
        simulated(name)


async def ran(name):
    """Return ``(session, problem, reference)`` of the stored whole-year run of an example."""
    context, result = simulated(name)
    return context.session, context.problem, result.output["reference"]


@example_names
async def test_a_run_summary_reads_in_readable_units(name):
    """Without a path every module is summarised, power in MW and temperatures in degC."""
    session, problem, reference = await ran(name)
    output = TOOLS.read_result.function(Context(session=session, problem=problem), reference)
    units = {field["max"]["unit"] for fields in output.values() for field in fields.values()}
    assert not units & {"W", "K", "Pa", "m3/s"}
    assert {"MW", "degC"} <= units


@example_names
async def test_a_path_summarises_that_module_only(name):
    """The module asked for, each field min, max and mean."""
    session, problem, reference = await ran(name)
    path = MODULES[name]
    arguments = {"reference": reference, "path": path}
    result = await call(TOOLS.read_result, arguments, session, problem=problem)
    assert set(result.output) == {path}


@example_names
async def test_a_series_has_times_values_and_a_readable_unit(name):
    """Path and field give gemini's series Value, window included, in MW for a power."""
    session, problem, reference = await ran(name)
    summary = TOOLS.read_result.function(Context(session=session, problem=problem), reference)
    path, field = next(
        (path, field)
        for path, fields in summary.items()
        for field, value in fields.items()
        if value["max"]["unit"] == "MW"
    )
    arguments = {"reference": reference, "path": path, "field": field}
    whole = (await call(TOOLS.read_result, arguments, session, problem=problem)).output
    first = whole["time"][0]
    windowed = await call(
        TOOLS.read_result, {**arguments, "start": first, "end": first}, session, problem=problem
    )
    assert whole["unit"] == "MW" and len(whole["time"]) == len(whole["value"])
    assert len(windowed.output["value"]) == 1


async def test_a_field_needs_a_path():
    """The model is told which input is missing."""
    result = await call(TOOLS.read_result, {"reference": "result/x", "field": "power"})
    assert result.is_error and result.output["error"]["path"] == "path"


async def test_an_unknown_reference_says_what_to_pass():
    """Only a reference that simulate returned reads."""
    result = await call(TOOLS.read_result, {"reference": "result/none"})
    assert result.output["error"]["code"] == "unknown_name"
    assert "simulate" in result.output["error"]["message"]


async def test_an_unknown_path_is_gemini_s_problem():
    """An unknown path comes back with the paths that exist."""
    session, problem, reference = await ran("shallow_district")
    arguments = {"reference": reference, "path": "heat_pum", "field": "x"}
    result = await call(TOOLS.read_result, arguments, session, problem=problem)
    assert result.is_error and "heat_pump" in result.output["error"]["message"]


def context(workspace=None, project="p1"):
    """Return a context inside a stand-in run."""
    return Context(project=project, session=StubSession(workspace=workspace))


def test_search_documents_searches_the_project():
    """The workspace of the run answers."""
    documents = {"p1": [{"id": "a", "title": "Pumps", "text": "the pump runs at 50 Hz"}]}
    output = search_documents.function(context(MemoryWorkspace(documents=documents)), "pump")
    assert output[0]["id"] == "a"


@pytest.mark.parametrize("options", [{"workspace": None}, {"project": None}])
def test_search_documents_needs_a_project(options):
    """A run without one gets an error result, not a crash."""
    arguments = {"workspace": MemoryWorkspace(), "project": "p1", **options}
    with pytest.raises(ToolError, match="no project"):
        search_documents.function(context(**arguments), "pump")


def test_both_only_read():
    """Reading needs no approval, and a replay reads again."""
    assert (TOOLS.read_result.effect, search_documents.effect) == ("read", "read")
