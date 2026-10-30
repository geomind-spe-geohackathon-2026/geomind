"""The state of a run."""

from geomind.engine.state import PendingAction, RunState
from geomind.types import Request, Usage


def test_a_new_state_is_running_and_empty():
    """Each state has its own containers."""
    first, second = RunState(), RunState()
    first.messages.append("x")
    assert second.messages == [] and second.status == "running" and second.usage == Usage()


def test_pending_action_holds_the_request():
    """A pause without a call is possible, as before an LLM call."""
    pending = PendingAction(request=Request(kind="approval", message="m"), point="llm")
    assert pending.call is None and pending.child is None
