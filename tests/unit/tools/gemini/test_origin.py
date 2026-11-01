"""The case the user gave: kept by set_case, compared by case_changes, approved by accept_case."""

import copy

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
from tests.fixtures.cases import example_case, example_names
from tests.fixtures.sessions import StubSession


def evolved(session, problem):
    """Return ``problem`` after the last change a session recorded."""
    return apply_changes(problem, session.changes[-1])


async def from_project(name):
    """Return ``(session, problem)`` after ``set_case(source="project")`` on an example."""
    session = StubSession(workspace=MemoryWorkspace(cases={"p": example_case(name)}))
    result = await call(set_case, {"source": "project"}, session, project="p")
    assert result.is_error is False, result.output
    return session, evolved(session, ProblemState())


async def changed(session, problem, changes):
    """Return the problem after ``set_case`` with ``changes`` on the state's case."""
    result = await call(set_case, {"changes": changes}, session, problem=problem)
    assert result.is_error is False, result.output
    return evolved(session, problem)


async def listed(session, problem):
    """Return the output of ``case_changes``."""
    return (await call(case_changes, {}, session, problem=problem)).output


@example_names
async def test_the_project_s_case_is_the_case_the_user_gave(name):
    """The origin is the project's case and its files; nothing differs from it yet."""
    session, problem = await from_project(name)
    assert problem.case_origin["case"] == example_case(name)[0]
    assert set(problem.case_origin["files"]) == {"demand.csv"}
    assert await listed(session, problem) == []


async def test_changes_in_the_same_call_as_the_project_are_not_the_origin():
    """``source="project"`` with changes keeps the project's case as the origin."""
    case = example_case("shallow_district")
    session = StubSession(workspace=MemoryWorkspace(cases={"p": case}))
    loosen = {"constraints": []}
    await call(set_case, {"source": "project", "changes": loosen}, session, project="p")
    problem = evolved(session, ProblemState())
    assert problem.case_origin["case"] == case[0] and problem.case["constraints"] == []


async def test_a_removed_constraint_is_listed_and_fails_verification():
    """Loosening the case is a change the user must approve; gemini is never asked."""
    session, problem = await from_project("hackathon_2026")
    first = problem.case["constraints"][0]
    problem = await changed(session, problem, {"constraints": problem.case["constraints"][1:]})
    assert await listed(session, problem) == [
        {"path": "constraints", "change": "removed", "given": first}
    ]
    verdict = case_changed(Context(session=session, problem=problem))
    assert verdict["passed"] is False
    assert verdict["failures"][0]["name"] == "case_changed"
    assert "constraints" in verdict["reason"]


async def test_a_demand_service_or_a_file_that_changed_is_listed():
    """A service dropped from the demand, and a file overwritten under its name, both count."""
    session, problem = await from_project("shallow_district")
    problem = await changed(session, problem, {"demand": {"cooling": None}})
    session.artifacts["case/demand.csv"] = session.artifacts["case/demand.csv"] + b"\n"
    paths = {item["path"] for item in await listed(session, problem)}
    assert paths == {"demand.cooling", "file demand.csv"}


async def test_the_first_case_of_a_chat_is_the_origin_and_later_changes_are_not():
    """A case set from the user's words is theirs; a change after it waits for approval."""
    session, problem = await from_project("shallow_district")
    data = copy.deepcopy(problem.case)
    fresh = StubSession()
    fresh.artifacts.update(session.artifacts)
    problem = await changed(fresh, ProblemState(), data)
    assert problem.case_origin["case"] == data
    problem = await changed(fresh, problem, {"assumptions": None})
    assert problem.case_origin["case"] == data
    assert [item["path"] for item in await listed(fresh, problem)] == ["assumptions"]


async def test_the_origin_comes_back_with_its_files():
    """``source="origin"`` restores the case and the file content the user gave."""
    session, problem = await from_project("shallow_district")
    given = session.artifacts["case/demand.csv"]
    problem = await changed(session, problem, {"constraints": []})
    session.artifacts["case/demand.csv"] = given + b"\n"
    result = await call(set_case, {"source": "origin"}, session, problem=problem)
    problem = evolved(session, problem)
    assert result.is_error is False
    assert session.artifacts["case/demand.csv"] == given
    assert await listed(session, problem) == []


async def test_accept_case_makes_the_changed_case_the_user_s():
    """After the user's approval nothing differs any more."""
    session, problem = await from_project("hackathon_2026")
    problem = await changed(session, problem, {"constraints": []})
    await call(accept_case, {}, session, problem=problem)
    problem = evolved(session, problem)
    assert problem.case_origin["case"]["constraints"] == []
    assert await listed(session, problem) == []


@pytest.mark.parametrize("path", ["/case", "/case/constraints", "/case_origin"])
async def test_update_state_never_writes_the_case(path):
    """Only set_case writes the case, after gemini validates it."""
    change = {"op": "replace", "path": path, "value": {}}
    result = await call(update_state, {"changes": [change]}, StubSession())
    assert result.output["error"]["code"] == "not_allowed"
    assert "set_case" in result.output["error"]["message"]
