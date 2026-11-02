"""The decision table of the hooks and the shipped hooks."""

import asyncio

import pytest

from geomind.engine import Context
from geomind.engine.hooks import (
    Cancellation,
    CostBudget,
    Hook,
    ProjectBudget,
    RequireApproval,
    TokenBudget,
    Verified,
    ask_hooks,
)
from geomind.engine.recovery import recover
from geomind.errors import BudgetError
from geomind.stores import MemoryUsageLedger
from geomind.tools.gemini.stored import save_design
from geomind.types import Action, Allow, Deny, Request, Usage
from tests.fixtures.cases import example_plant
from tests.fixtures.runs import (
    EXECUTED,
    Lead,
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
from tests.fixtures.stored_runs import variant_run, warm_runs


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


async def test_verified_lets_a_run_without_a_design_finish():
    """An answer that proposes no design has nothing to verify."""
    result, _, _ = await run([says()], hooks=[Verified()])
    assert (result.status, result.stop_reason) == ("done", "answer")


@pytest.mark.parametrize("point", ["llm", "tool", "finish"])
async def test_request_pauses_at_every_point(point):
    """The run returns ``waiting``, and the log holds the pending action."""
    script = [uses(call("lookup", key="k")), says()]
    result, engine, events = await run(script, hooks=[Fixed(point, ASK)])
    assert (result.status, result.stop_reason) == ("waiting", "request")
    assert result.request.id.startswith("request-")
    assert of_type(events, "request")[0].point == point
    assert recover(events).pending.point == point
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


ANSWER = Action(text="Here is the design.")


@pytest.fixture(scope="module")
def stored():
    """Return the hackathon design run on its case and under a 15 MW cooling peak."""
    warm_runs()
    base, design, passing = variant_run("hackathon_2026", "base")
    peak, _, failing = variant_run("hackathon_2026", "cooling_peak")
    asyncio.run(save_design(base, "other", example_plant("hackathon_2026", "HeatingPlant")))
    return {"base": base, "peak": peak, "design": design, "passing": passing, "failing": failing}


def decide(context, design=None, verification=None):
    """Return the hook's decision on a final answer, for a problem state of a context."""
    problem = context.problem.model_copy(
        update={"design": design or {}, "verification": verification or {}}
    )
    return asyncio.run(
        Verified().before_finish(Context(problem=problem, session=context.session), None, ANSWER)
    )


def test_a_design_that_passed_gemini_s_checks_reaches_the_user(stored):
    """The hook verifies the named result again, and it passes."""
    decision = decide(
        stored["base"], {"reference": stored["design"]}, {"result": stored["passing"]}
    )
    assert decision is None


def test_a_design_that_fails_a_check_is_refused_with_the_failures(stored):
    """The reason names the failed check and its domain, so the model knows what to fix."""
    verification = {"result": stored["failing"]}
    decision = decide(stored["peak"], {"reference": stored["design"]}, verification)
    assert isinstance(decision, Deny)
    assert "cold_delivered (sizing)" in decision.reason


def test_a_passed_flag_written_by_the_model_is_not_trusted(stored):
    """Only gemini's checks on the stored run count."""
    verification = {"result": stored["failing"], "passed": True}
    decision = decide(stored["peak"], {"reference": stored["design"]}, verification)
    assert isinstance(decision, Deny)


def test_a_design_without_a_verified_result_is_refused(stored):
    """A design with no result to check never reaches the user."""
    decision = decide(stored["base"], {"reference": stored["design"]})
    assert isinstance(decision, Deny)
    assert "check_results" in decision.reason


def test_a_result_of_another_design_is_stale(stored):
    """After a change, earlier results of a design are stale and never reused."""
    decision = decide(stored["base"], {"reference": "design/other"}, {"result": stored["passing"]})
    assert isinstance(decision, Deny)
    assert "stale" in decision.reason


def test_an_unknown_result_is_refused(stored):
    """A reference simulate never returned cannot verify anything."""
    decision = decide(stored["base"], {"reference": stored["design"]}, {"result": "result/missing"})
    assert isinstance(decision, Deny)


def test_a_nested_run_hands_its_design_back_without_the_hook(stored):
    """Only the root run answers the user; a designer may return a failing design to its loop."""
    context = stored["peak"]
    context.session.state.parent = "run-root"
    try:
        decision = decide(context, {"reference": stored["design"]}, {"result": stored["failing"]})
    finally:
        context.session.state.parent = None
    assert decision is None


async def test_a_budget_counts_the_runs_above_a_nested_run():
    """A delegate's calls are denied once the whole run is over the budget, not its own usage."""
    from tests.fixtures.runs import Lead

    expensive = Usage(input_tokens=900, output_tokens=0, cost=0.9)
    script = [
        uses(call("helper", task="t"), usage=expensive),
        uses(call("lookup", key="k")),
        says("found"),
        says("end"),
    ]
    result, _, events = await run(script, agent=Lead(), hooks=[TokenBudget(910)])
    nested = [e for e in events if e.type == "run.finished" and e.parent is not None]
    assert nested[0].stop_reason == "denied"
    assert "token budget: used 915 of 910" in nested[0].message


def reason_of(events):
    """Return the message the root run ended with."""
    return next(e.message for e in events if e.type == "run.finished" and e.parent is None)


def prior(tokens=0, cost=0.0):
    """Return a ledger where the project ``p`` already spent this much in earlier runs."""
    ledger = MemoryUsageLedger()
    ledger.add("p", Usage(input_tokens=tokens, cost=cost))
    return ledger


async def test_project_budget_under_the_cap_goes_ahead():
    """Earlier spending and this run together under the caps change nothing."""
    budget = ProjectBudget(prior(100, 1.0), "p", max_tokens=1000, max_cost=5.0)
    result, _, _ = await run([says("end")], hooks=[budget])
    assert result.answer == "end"


async def test_project_budget_denies_before_the_call_at_the_cap():
    """Earlier spending alone at the cap denies the first call, and the reason says what."""
    budget = ProjectBudget(prior(100), "p", max_tokens=100)
    result, _, events = await run([says("never")], hooks=[budget])
    assert (result.stop_reason, result.steps) == ("denied", 1)
    assert not [e for e in events if e.type == "llm.completed"]
    assert "project token budget: p used 100 of 100" in reason_of(events)


async def test_project_budget_adds_this_run_to_earlier_spending():
    """The first call passes at 15 of 20 tokens, the second sees 30."""
    budget = ProjectBudget(prior(5), "p", max_tokens=20)
    script = [uses(call("lookup", key="k")), says("never")]
    result, _, events = await run(script, hooks=[budget])
    assert (result.stop_reason, result.steps) == ("denied", 2)
    assert "project token budget: p used 20 of 20" in reason_of(events)


async def test_project_budget_caps_the_cost():
    """The cost cap denies with the cost in the reason."""
    budget = ProjectBudget(prior(0, 2.0), "p", max_cost=2.0)
    _, _, events = await run([says("never")], hooks=[budget])
    assert "project cost budget: p used 2.0 of 2.0" in reason_of(events)


async def test_project_budget_counts_nested_runs():
    """A delegate's calls count against the project, with the runs above it."""
    expensive = Usage(input_tokens=900, output_tokens=0, cost=0.9)
    script = [
        uses(call("helper", task="t"), usage=expensive),
        uses(call("lookup", key="k")),
        says("found"),
        says("end"),
    ]
    budget = ProjectBudget(prior(0), "p", max_tokens=910)
    _, _, events = await run(script, agent=Lead(), hooks=[budget])
    nested = [e for e in events if e.type == "run.finished" and e.parent is not None]
    assert nested[0].stop_reason == "denied"
    assert "project token budget: p used 915 of 910" in nested[0].message


def test_project_budget_without_a_cap_is_an_error():
    """There is no default cap."""
    with pytest.raises(BudgetError, match="expected max_tokens or max_cost"):
        ProjectBudget(MemoryUsageLedger(), "p")


class CountingLedger(MemoryUsageLedger):
    """Count the reads."""

    reads = 0

    def spent(self, project_id):
        """Count one read."""
        self.reads += 1
        return super().spent(project_id)


async def test_project_budget_reads_the_ledger_once_per_run():
    """Several calls of a run, nested runs included, read the ledger once."""
    ledger = CountingLedger()
    script = [uses(call("lookup", key="k")), uses(call("lookup", key="k")), says("end")]
    await run(script, hooks=[ProjectBudget(ledger, "p", max_tokens=1000)])
    assert ledger.reads == 1
