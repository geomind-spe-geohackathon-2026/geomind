"""The case the user gave: kept by set_case, compared by case_changes, approved by accept_case."""

import copy
import json

import pytest

from geomind.context import ProblemState
from geomind.context.state import apply_changes
from geomind.engine import Context
from geomind.stores import MemoryWorkspace
from geomind.tools import update_state
from geomind.tools.gemini.case import set_case
from geomind.tools.gemini.origin import accept_case, case_changes
from geomind.verify.design import case_changed
from tests.fixtures.calls import call
from tests.fixtures.cases import example_case, example_names, warm_gemini
from tests.fixtures.sessions import StubSession


@pytest.fixture
def asked():
    """Write economics as ``ask_economics`` does after approve all (QA-320)."""
    from geomind.tools.gemini.case import ASKED_ECONOMICS

    token = ASKED_ECONOMICS.set(True)
    yield
    ASKED_ECONOMICS.reset(token)



@pytest.fixture(scope="module", autouse=True)
def warmed():
    """Pay for the gemini import and the first case build outside the timed calls."""
    warm_gemini()


def evolved(session, problem):
    """Return ``problem`` after the last change a session recorded."""
    return apply_changes(problem, session.changes[-1])


async def from_project(name):
    """Return ``(session, problem)`` after ``set_case(source="project")`` on an example."""
    session = StubSession(workspace=MemoryWorkspace(cases={"p": example_case(name)}))
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error is False, result.output
    return session, evolved(session, ProblemState())


async def changed(session, problem, changes=None, **arguments):
    """Return the problem after ``set_case`` with ``changes`` or other arguments on its case."""
    arguments = {"changes": changes, **arguments} if changes else arguments
    result = await call(set_case, arguments, session, problem=problem)
    assert result.is_error is False, result.output
    return evolved(session, problem)


async def listed(session, problem):
    """Return the output of ``case_changes``."""
    return (await call(case_changes, {}, session, problem=problem)).output


@example_names
async def test_the_project_s_case_is_the_case_the_user_gave(name):
    """The origin is the project's case and every file it names; nothing differs from it yet."""
    session, problem = await from_project(name)
    assert problem.case_origin["case"] == example_case(name)[0]
    assert set(problem.case_origin["files"]) == {"data/demand.csv", "economics.json"}
    assert await listed(session, problem) == []


async def test_changes_in_the_same_call_as_the_project_are_not_the_origin():
    """``source="project"`` with changes keeps the project's case as the origin."""
    case = example_case("shallow_district")
    session = StubSession(workspace=MemoryWorkspace(cases={"p": case}))
    arguments = {"source": "project", "requirements": {"heat_delivered": None}}
    await call(set_case, arguments, session, project="p")
    problem = evolved(session, ProblemState())
    assert problem.case_origin["case"] == case[0]
    assert len(problem.case["requirements"]) == len(case[0]["requirements"]) - 1


async def test_a_removed_requirement_is_listed_by_name_and_fails_verification():
    """Loosening the case is a change the user must approve; gemini is never asked."""
    session, problem = await from_project("hackathon_2026")
    first = problem.case["requirements"][0]
    problem = await changed(session, problem, requirements={first["name"]: None})
    assert await listed(session, problem) == [
        {
            "path": f"requirements.{first['name']}",
            "change": "removed",
            "given": first,
            "now": None,
        }
    ]
    verdict = case_changed(Context(session=session, problem=problem))
    assert verdict["passed"] is False
    assert verdict["failures"][0]["name"] == "case_changed"
    assert f"requirements.{first['name']}" in verdict["reason"]


async def test_a_changed_requirement_is_listed_as_changed_and_an_added_one_as_added():
    """The same name with other limits changed; a new name is added."""
    session, problem = await from_project("hackathon_2026")
    count = {"on": "doublet", "quantity": "count", "min": 1, "max": 2}
    extra = {"on": "doublet", "quantity": "count", "min": 1, "max": 5}
    problem = await changed(session, problem, requirements={"doublet_count": count, "extra": extra})
    found = {item["path"]: item["change"] for item in await listed(session, problem)}
    assert found == {"requirements.doublet_count": "changed", "requirements.extra": "added"}


@pytest.mark.usefixtures("asked")
async def test_a_change_of_the_economics_is_a_change_of_the_case():
    """The economics file is part of the case: the change is listed and verification fails."""
    session, problem = await from_project("shallow_district")
    patch = {"analysis_period": {"value": 20, "unit": "yr"}}
    problem = await changed(session, problem, economics=patch)
    assert [item["path"] for item in await listed(session, problem)] == ["file economics.json"]
    verdict = case_changed(Context(session=session, problem=problem))
    assert verdict["failures"][0]["name"] == "case_changed"
    assert "file economics.json" in verdict["reason"]


async def test_a_demand_service_or_a_file_that_changed_is_listed():
    """A service dropped from the demand, and a file overwritten under its name, both count."""
    session, problem = await from_project("shallow_district")
    problem = await changed(session, problem, {"demand": {"cooling": None}})
    session.artifacts["case/data/demand.csv"] = session.artifacts["case/data/demand.csv"] + b"\n"
    paths = {item["path"] for item in await listed(session, problem)}
    assert paths == {"demand.cooling", "file data/demand.csv"}


@pytest.mark.usefixtures("asked")
async def test_the_first_case_of_a_chat_is_the_origin_and_later_changes_are_not():
    """A case set from the user's words is theirs; a change after it waits for approval."""
    session, problem = await from_project("shallow_district")
    data = copy.deepcopy(problem.case)
    fresh = StubSession()
    fresh.artifacts.update(session.artifacts)
    named = {item["name"]: item for item in data.pop("requirements")}
    economics = json.loads(session.artifacts["case/economics.json"])
    data.pop("economics")
    problem = await changed(fresh, ProblemState(), data, requirements=named, economics=economics)
    data = problem.case
    assert problem.case_origin["case"] == data
    problem = await changed(fresh, problem, {"about": {"note": "x"}})
    assert problem.case_origin["case"] == data
    assert [item["path"] for item in await listed(fresh, problem)] == ["about"]


@pytest.mark.usefixtures("asked")
async def test_the_origin_comes_back_with_its_files():
    """``source="origin"`` restores the case and the file content the user gave."""
    session, problem = await from_project("shallow_district")
    given = session.artifacts["case/data/demand.csv"]
    economics = session.artifacts["case/economics.json"]
    patch = {"analysis_period": {"value": 20, "unit": "yr"}}
    problem = await changed(session, problem, economics=patch)
    session.artifacts["case/data/demand.csv"] = given + b"\n"
    result = await call(set_case, {"source": "origin"}, session, problem=problem)
    problem = evolved(session, problem)
    assert result.is_error is False, result.output
    assert session.artifacts["case/data/demand.csv"] == given
    assert session.artifacts["case/economics.json"] == economics
    assert await listed(session, problem) == []


async def test_accept_case_makes_the_changed_case_the_user_s():
    """After the user's approval nothing differs any more."""
    session, problem = await from_project("hackathon_2026")
    problem = await changed(session, problem, requirements={"doublet_count": None})
    await call(accept_case, {}, session, problem=problem)
    problem = evolved(session, problem)
    names = [item["name"] for item in problem.case_origin["case"]["requirements"]]
    assert "doublet_count" not in names
    assert await listed(session, problem) == []


@pytest.mark.parametrize("path", ["/case", "/case/requirements", "/case_origin"])
async def test_update_state_never_writes_the_case(path):
    """Only set_case writes the case, after gemini validates it."""
    change = {"op": "replace", "path": path, "value": {}}
    result = await call(update_state, {"changes": [change]}, StubSession())
    assert result.output["error"]["code"] == "not_allowed"
    assert "set_case" in result.output["error"]["message"]
