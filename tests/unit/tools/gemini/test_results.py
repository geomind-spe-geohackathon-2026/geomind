"""The tools over a stored run's results and the project's documents."""

import pytest

import geomind as gd
from geomind.engine import Context
from geomind.errors import ToolError
from geomind.stores import MemoryWorkspace
from geomind.tools import search_rag
from tests.fixtures.calls import call
from tests.fixtures.cases import EXAMPLES, example_case, example_names, example_plant
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
    """The module asked for, each field min, max and mean, and how long it ran."""
    session, problem, reference = await ran(name)
    path = MODULES[name]
    arguments = {"reference": reference, "path": path}
    result = await call(TOOLS.read_result, arguments, session, problem=problem)
    assert set(result.output) == {path, "operation"}
    operation = result.output["operation"]
    assert 0 < operation["operating_days"] <= operation["steps"]


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
    summary = whole["summary"]
    assert summary["max"]["value"] == max(whole["value"])
    assert summary["max"]["time"] == whole["time"][whole["value"].index(max(whole["value"]))]
    assert summary["active_steps"] == sum(1 for number in whole["value"] if number)


async def test_a_field_needs_a_path():
    """The model is told which input is missing."""
    result = await call(TOOLS.read_result, {"reference": "result/x", "field": "power"})
    assert result.is_error and result.output["error"]["path"] == "path"


async def test_a_cost_name_as_path_names_the_tool_that_has_it():
    """QA-209: read_result reads module columns; costs are estimate_costs', KPIs compute_kpis'."""
    for path in ("costs", "lcts", "annualised_cost"):
        result = await call(TOOLS.read_result, {"reference": "result/x", "path": path})
        message = result.output["error"]["message"]
        assert result.is_error and "estimate_costs" in message and "compute_kpis" in message


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
    output = search_rag.function(context(MemoryWorkspace(documents=documents)), "pump")
    assert output["matches"][0]["id"] == "a"


def test_the_same_words_twice_in_one_step_note_the_later_call_in_any_order_they_run():
    """#131: the note follows the order of the calls in the run's conversation.

    The case lead searched these two queries in one step; the live run noted the first, a replay
    the second, as they ran together, so ``geomind replay`` failed.
    """
    from geomind.types import Message, ToolCall

    documents = {"p1": [{"id": "a", "title": "Air", "text": "the site air pressure"}]}
    workspace = MemoryWorkspace(documents=documents)
    first = ToolCall(
        id="c1", name="search_rag", input={"query": "site.air.pressure atmospheric pressure site"}
    )
    second = ToolCall(
        id="c2", name="search_rag", input={"query": "atmospheric pressure air pressure site"}
    )
    messages = [Message(role="assistant", tool_calls=(first, second))]
    run = Context(messages=messages, project="p1", session=StubSession(workspace=workspace))
    for order in ((second, first), (first, second)):
        notes = {
            item.id: search_rag.function(run.for_call(item.id), **item.input) for item in order
        }
        assert "already searched" in notes["c2"].get("note", "")
        assert "already searched" not in notes["c1"].get("note", "")


@pytest.mark.parametrize("options", [{"workspace": None}, {"project": None}])
def test_search_documents_needs_a_project(options):
    """A run without one gets an error result, not a crash."""
    arguments = {"workspace": MemoryWorkspace(), "project": "p1", **options}
    with pytest.raises(ToolError, match="no project"):
        search_rag.function(context(**arguments), "pump")


def test_both_only_read():
    """Reading needs no approval, and a replay reads again."""
    assert (TOOLS.read_result.effect, search_rag.effect) == ("read", "read")


class ProjectWorkspace:
    """A project with one plant version and one Study-page result of it (QA-165)."""

    def __init__(self, case_version=1):
        """Keep the example's plant as version 1 and its case at ``case_version``."""
        self.case_version = case_version

    def project_designs(self, project_id):
        """Return one page study with its result."""
        result = {"id": "c0661c15-aaaa-bbbb", "plant_version": 1, "case_version": 1}
        return {"plants": [], "studies": [{"id": "s1", "name": "run v1", "result": result}]}

    def plant_version(self, project_id, version):
        """Return the example's plant dict as version 1."""
        return example_plant("shallow_district").to_dict() if version == 1 else None

    def plants(self, project_id):
        """No named plants."""
        return {}

    def case(self, project_id):
        """Return the example's case."""
        return example_case("shallow_district")

    def project_state(self, project_id):
        """Return the case version."""
        return {"case_version": self.case_version}


async def test_a_project_result_is_readable_by_its_id():
    """QA-165: the result of the Study page is read by its id, in any form an agent writes."""
    session = StubSession(workspace=ProjectWorkspace())
    for reference in ("result/c0661c15-aaaa-bbbb", "c0661c15aaaabbbb", "result-c0661c15-aaaa-bbbb"):
        result = await call(TOOLS.read_result, {"reference": reference}, session, project="p1")
        assert not result.is_error, result.output
    old = StubSession(workspace=ProjectWorkspace(case_version=2))
    refused = await call(
        TOOLS.read_result, {"reference": "result/c0661c15-aaaa-bbbb"}, old, project="p1"
    )
    assert refused.is_error and "case version 1" in refused.output["error"]["message"]


async def test_a_group_path_gives_each_of_its_modules():
    """QA-262: d0 is the doublet; its parts are read at once, not refused."""
    session, problem, reference = await ran("hackathon_2026")
    result = await call(
        TOOLS.read_result, {"reference": reference, "path": "d0"}, session, problem=problem
    )
    assert not result.is_error and result.output["group"] == "d0"
    assert {"d0.reservoir", "d0.well", "d0.esp", "d0.riser"} <= set(result.output["modules"])
    assert "operation" in result.output["modules"]["d0.esp"]


def test_a_match_is_a_snippet_around_the_query_with_the_call_that_reads_it_whole():
    """QA-272: whole chunks of 1.1-1.5k characters per match filled the case lead's context."""
    from geomind.tools.gemini.results import SNIPPET_CHARS

    text = "x" * 900 + " the pump runs at 50 Hz " + "y" * 900
    documents = {"p1": [{"id": "a", "title": "Pumps", "text": text}]}
    match = search_rag.function(context(MemoryWorkspace(documents=documents)), "pump")["matches"][0]
    assert "pump runs at 50 Hz" in match["text"]
    assert len(match["text"]) <= SNIPPET_CHARS + len("......")
    assert match["read"].startswith("read_rag(")


def test_a_file_read_whole_in_this_run_is_named_not_searched_again():
    """QA-272: every answer began with the brief's page 1, already read whole."""
    from geomind.tools.gemini.results import read_whole
    from geomind.types import Message, ToolCall

    whole = ToolCall(id="r1", name="read_rag", input={"name": "brief.pdf"})
    part = ToolCall(id="r2", name="read_rag", input={"name": "demand.csv", "length": 1200})
    now = ToolCall(id="s1", name="search_rag", input={"query": "pump"})
    messages = [
        Message(role="assistant", tool_calls=(whole, part)),
        Message(role="assistant", tool_calls=(now,)),
    ]
    run = Context(messages=messages, project="p1", session=StubSession())
    assert read_whole(run.for_call("s1")) == {"brief.pdf"}
