"""The skeleton of the coordinator."""

from typing import get_args

import pytest
from pydantic import ValidationError

from geomind.agents import Coordinator, Route
from geomind.run import AGENTS, LOOPS
from geomind.runtime import FIXED_CHEAP_MODEL
from tests.unit.agents.structure import check_skeleton


def test_the_skeleton_is_complete():
    """It constructs, its prompt has the six headings and its sections are in order."""
    check_skeleton(Coordinator, "coordinator")


def test_it_declares_a_typed_route():
    """A route is an answer, or a loop with an agent."""
    agent = Coordinator()
    assert agent.output.kind is Route
    assert agent.output.validate({"kind": "answer", "answer": "hi"})["answer"] == "hi"
    assert agent.output.validate({"kind": "loop"})["agent"] == "analyst"


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
    assert Coordinator().model.resolved_name() == FIXED_CHEAP_MODEL
    assert set(AGENTS) == {"analyst", "code_assistant"}
