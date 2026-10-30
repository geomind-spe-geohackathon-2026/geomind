"""The decision table of the hooks and the shipped hooks."""

import pytest

from geomind.engine.hooks import (
    Cancellation,
    CostBudget,
    Hook,
    RequireApproval,
    TokenBudget,
    ask_hooks,
)
from geomind.types import Allow, Deny, Request
from tests.fixtures.runs import (
    EXECUTED,
    Worker,
    call,
    context,
    engine_for,
    of_type,
    run,
    says,
    types,
    uses,
)


class Fixed(Hook):
    """Return one decision at one point."""

    def __init__(self, point, decision):
        """Keep the point and the decision."""
        self.point = point
        self.decision = decision

    def before_llm_call(self, context, agent, messages):
        """Decide before an LLM call."""
        return self.decision if self.point == "llm" else None

    def before_tool_call(self, context, agent, call):
        """Decide before a tool call."""
        return self.decision if self.point == "tool" else None

    async def before_finish(self, context, agent, action):
        """Decide before the answer, asynchronously on purpose."""
        return self.decision if self.point == "finish" else None


DENY = Deny(reason="no")
ASK = Request(kind="approval", message="ok?")


async def test_none_lets_everything_pass():
    """A hook with no objection changes nothing."""
    result, _, _ = await run([uses(call("lookup", key="k")), says("end")], hooks=[Hook()])
    assert result.answer == "end"


async def test_deny_before_an_llm_call_stops_the_run():
    """The run stops as ``denied`` and logs the reason."""
    result, engine, events = await run([says()], hooks=[Fixed("llm", DENY)])
    assert (result.stop_reason, result.status) == ("denied", "failed")
    assert of_type(events, "run.finished")[0].message == "no"
    assert engine.llm.llm.calls == []


async def test_deny_before_a_tool_call_makes_the_reason_its_result():
    """The tool is skipped and the run goes on."""
    result, _, events = await run(
        [uses(call("lookup", key="k")), says("end")], hooks=[Fixed("tool", DENY)]
    )
    assert result.answer == "end" and EXECUTED == []
    recorded = of_type(events, "tool.result")[0]
    assert (recorded.output, recorded.is_error, recorded.source) == ("no", True, "denied")


async def test_deny_before_finish_feeds_the_reason_back():
    """A refused plain answer becomes a message; the model tries again."""

    class Once(Hook):
        refused = False

        def before_finish(self, context, agent, action):
            if self.refused:
                return None
            self.refused = True
            return Deny(reason="not yet")

    result, engine, _ = await run([says("first"), says("second")], hooks=[Once()])
    assert result.answer == "second"
    sent = engine.llm.llm.calls[1]["messages"]
    assert [m.content for m in sent if m.role == "user"][-1] == "not yet"


async def test_deny_of_the_finish_tool_is_its_result():
    """A refused ``finish`` is a tool result; the model tries again."""

    class Once(Hook):
        refused = False

        def before_finish(self, context, agent, action):
            if self.refused:
                return None
            self.refused = True
            return Deny(reason="verify first")

    result, _, events = await run(
        [uses(call("finish", answer="a")), uses(call("finish", "c2", answer="b"))], hooks=[Once()]
    )
    assert (result.stop_reason, result.answer) == ("finish", "b")
    assert of_type(events, "tool.result")[0].output == "verify first"


@pytest.mark.parametrize("point", ["llm", "tool", "finish"])
async def test_request_pauses_at_every_point(point):
    """The run returns ``waiting`` and the event comes after the checkpoint is saved."""
    script = [uses(call("lookup", key="k")), says()]
    result, engine, events = await run(script, hooks=[Fixed(point, ASK)])
    assert (result.status, result.stop_reason) == ("waiting", "request")
    assert result.request.id.startswith("request-")
    assert of_type(events, "request")[0].point == point
    assert engine.store.load_checkpoint(result.run_id)["pending"]["point"] == point
    assert "run.finished" not in types(events)


async def test_allow_changes_the_input():
    """A hook can correct an input, and the log shows the change."""

    class Correct(Hook):
        def before_tool_call(self, context, agent, call):
            return Allow(input={"key": "fixed"})

    _, _, events = await run([uses(call("lookup", key="wrong")), says()], hooks=[Correct()])
    assert of_type(events, "tool.result")[0].output == "value of fixed"
    assert of_type(events, "permission")[0].input == {"key": "fixed"}


async def test_allow_does_not_skip_the_rules():
    """An allow from a hook still meets the permission rules."""

    class Yes(Hook):
        def before_tool_call(self, context, agent, call):
            return Allow()

    engine = engine_for([uses(call("save_note", text="x"))], hooks=[Yes()], permissions=None)
    result = await engine.run(Worker(), context())
    assert result.status == "waiting" and EXECUTED == []


async def test_ask_hooks_returns_the_first_objection():
    """Later hooks are not asked."""
    first, second = Fixed("tool", DENY), Fixed("tool", ASK)
    decision, name = await ask_hooks([first, second], "before_tool_call", None, None, call("t"))
    assert (decision, name) == (DENY, "Fixed")


async def test_token_budget_stops_with_denied():
    """Over the budget the next LLM call is denied."""
    result, _, _ = await run(
        [uses(call("lookup", key="k")), uses(call("lookup", "c2", key="k")), says()],
        hooks=[TokenBudget(20)],
    )
    assert (result.stop_reason, result.steps) == ("denied", 3)


async def test_token_budget_allows_within_the_limit():
    """Under the budget nothing happens."""
    result, _, _ = await run([says("end")], hooks=[TokenBudget(1000)])
    assert result.answer == "end"


async def test_cost_budget_stops_with_denied():
    """Cost has its own limit."""
    result, _, _ = await run([uses(call("lookup", key="k")), says()], hooks=[CostBudget(0.005)])
    assert result.stop_reason == "denied"


async def test_require_approval_pauses_before_the_tool():
    """It works as an ask rule."""
    result, _, events = await run(
        [uses(call("lookup", key="k"))], hooks=[RequireApproval(["lookup"])]
    )
    assert result.status == "waiting" and EXECUTED == []
    assert of_type(events, "permission")[0].rule == "ask:lookup"
    assert result.request.call_id == "c1"


async def test_cancellation_stops_before_an_llm_call():
    """The caller's function decides."""
    result, _, _ = await run([says()], hooks=[Cancellation(lambda: True)])
    assert (result.stop_reason, result.status) == ("cancelled", "cancelled")


async def test_cancellation_stops_before_a_tool_call():
    """A cancellation between the LLM call and the tool stops the tool."""
    answers = iter([False, True])
    result, _, _ = await run(
        [uses(call("lookup", key="k"))], hooks=[Cancellation(lambda: next(answers))]
    )
    assert result.stop_reason == "cancelled" and EXECUTED == []


async def test_cancellation_stops_before_the_answer():
    """Even a finished thought can be cancelled."""
    answers = iter([False, True])
    result, _, _ = await run([says()], hooks=[Cancellation(lambda: next(answers))])
    assert result.stop_reason == "cancelled"
