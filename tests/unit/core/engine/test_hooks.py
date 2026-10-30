"""Hooks: the shipped ones."""

from swarmax.core.engine.hooks import Cancellation, TokenBudget
from tests.fixtures.runs import call, run, says, uses


async def test_token_budget_stops_with_denied():
    """Over the budget the next LLM call is denied."""
    result, _, _ = await run([uses(call("lookup", key="k")), says()], hooks=[TokenBudget(5)])
    assert (result.stop_reason, result.status) == ("denied", "failed")


async def test_cancellation_stops_with_cancelled():
    """The caller's function decides."""
    result, _, _ = await run([says()], hooks=[Cancellation(lambda: True)])
    assert (result.stop_reason, result.status) == ("cancelled", "cancelled")
