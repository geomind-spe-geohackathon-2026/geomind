"""The coordinator: it routes a message to an answer or a loop."""

from typing import get_args

import pytest
from pydantic import ValidationError

from geomind import runtime
from geomind.agents import Coordinator, Route
from geomind.run import AGENTS, LOOPS
from tests.unit.agents.structure import check_complete


def test_it_is_complete():
    """No tools: it answers with a route; every heading of its prompt is filled."""
    check_complete(Coordinator, "project/coordinator", [])


def test_it_declares_a_typed_route():
    """A route is an answer, or a loop with an agent."""
    agent = Coordinator()
    assert agent.output.kind is Route
    assert agent.output.validate({"kind": "answer", "answer": "hi"})["answer"] == "hi"
    assert agent.output.validate({"kind": "loop"})["agent"] == "analysis_lead"


def test_a_route_names_only_rows_of_the_tables():
    """``run.py`` sits to the right of the agents, so this test keeps the lists equal."""
    assert get_args(Route.model_fields["loop"].annotation) == tuple(LOOPS)
    assert get_args(Route.model_fields["agent"].annotation) == tuple(AGENTS)


def test_an_unknown_loop_is_refused():
    """A wrong name goes back to the model as output feedback."""
    with pytest.raises(ValidationError):
        Route(kind="loop", loop="other")


def test_it_is_cheap_and_not_routed_yet():
    """``Run`` does not call it, and skeletons are no rows of the table."""
    assert Coordinator().model.resolved_name() == runtime.get("coordinator_model")
    assert set(AGENTS) == {"analysis_lead"}


class SavedCase:
    """A project whose saved case holds another permeability than the chat's (QA-266)."""

    def __init__(self, permeability):
        """Keep the saved permeability."""
        self.permeability = permeability

    def case(self, project_id):
        """Return the saved case and no files."""
        return {"site": {"reservoir": {"permeability": self.permeability}}}, {}


def chat_with(saved):
    """Return a context whose chat case holds 150 mD and whose project saved ``saved``."""
    from geomind.engine import Context
    from geomind.context.state import ProblemState
    from geomind.types import Message
    from tests.fixtures.sessions import StubSession

    case = {"site": {"reservoir": {"permeability": {"value": 150, "unit": "mD"}}}}
    return Context(
        project="p1",
        session=StubSession(workspace=SavedCase(saved)),
        problem=ProblemState(case=case),
        messages=[Message(role="user", content="I saved the case form again.")],
    )


async def test_qa_266_a_newer_saved_case_routes_to_the_project_loop_by_rule():
    """QA-266: the second hand-saved change is loaded, never answered from the old case."""
    from geomind.agents.project.lead import has_project_case, project_case_changes

    context = chat_with({"value": 175, "unit": "mD"})
    assert project_case_changes(context) == ["site.reservoir.permeability 150 mD -> 175 mD"]
    assert has_project_case(context)
    action = await Coordinator().forward(context)
    route = Route.model_validate_json(action.text)
    assert (route.kind, route.loop) == ("loop", "project")
    assert "175 mD" in route.task
    same = chat_with({"value": 150, "unit": "mD"})
    assert project_case_changes(same) == [] and not has_project_case(same)
