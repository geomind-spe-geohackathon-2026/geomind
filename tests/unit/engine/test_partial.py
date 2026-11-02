"""The partial answer of a run that a limit stopped, and the budgets that fit a call."""

import threading

import pytest
from pydantic import BaseModel

from geomind.agents import Output
from geomind.context import ProblemState
from geomind.context.state import Assumption, Question, Result
from geomind.engine import Engine, Permissions
from geomind.engine.callbacks import Callback
from geomind.engine.hooks import CostBudget, Hook, ProjectBudget, TimeLimit, TokenBudget
from geomind.errors import BudgetError
from geomind.stores import MemoryUsageLedger
from geomind.types import Deny, Usage
from tests.fixtures.metered import PRICES, Metered
from tests.fixtures.runs import Worker, call, context, of_type, says, uses

CAP = 0.01


def looking(count):
    """Return a script of ``count`` lookups."""
    return [uses(call("lookup", f"c{n}", key="k")) for n in range(count)]


async def drive(llm, context_=None, agent=None, max_steps=None, hooks=(), callbacks=()):
    """Run the agent; return ``(result, events)``."""
    engine = Engine(
        llm=llm, permissions=Permissions(mode="auto"), hooks=list(hooks), callbacks=list(callbacks)
    )
    start = context_ or context()
    result = await engine.run(agent or Worker(), start, max_steps=max_steps)
    return result, engine.store.load_events(start.run_id)


def spent(events):
    """Return the cost of every completion of a log."""
    return sum(e.completion.usage.cost for e in events if e.type == "llm.completed")


async def test_a_run_under_a_small_cost_cap_ends_at_or_below_it():
    """The call's max_tokens is lowered to what fits, so the cap is never passed."""
    llm = Metered(looking(8))
    result, events = await drive(llm, hooks=[CostBudget(CAP, prices=PRICES)])
    assert result.stop_reason == "denied"
    assert 0 < spent(events) <= CAP
    assert min(item["max_tokens"] for item in llm.settings) < 1000


async def test_a_call_whose_input_does_not_fit_is_denied_before_it_is_made():
    """With 0.001 USD even the input of the first call does not fit."""
    llm = Metered(looking(2))
    result, events = await drive(llm, hooks=[CostBudget(0.001, prices=PRICES)])
    assert (result.stop_reason, llm.calls) == ("denied", 0)
    assert not of_type(events, "llm.completed")


async def test_the_agents_own_max_tokens_is_kept_when_it_already_fits():
    """A limit below the room is not raised."""
    llm = Metered([says("ok")])
    agent = Worker()
    object.__setattr__(agent, "model", agent.model.model_copy(update={"max_tokens": 5}))
    await drive(llm, agent=agent, hooks=[CostBudget(1.0, prices=PRICES)])
    assert llm.settings[0]["max_tokens"] == 5


async def test_a_token_cap_fits_a_call_when_the_input_is_bounded():
    """The output limit is what the cap leaves after the input bound."""
    llm = Metered(looking(8))
    result, events = await drive(llm, hooks=[TokenBudget(4000, bound_input=True)])
    used = sum(
        e.completion.usage.input_tokens + e.completion.usage.output_tokens
        for e in events
        if e.type == "llm.completed"
    )
    assert result.stop_reason == "denied" and used <= 4000


async def test_a_budget_ends_with_a_partial_answer_that_keeps_the_stop_reason():
    """Nothing is lost at a stop: the answer is built from the state, with no model call."""
    problem = ProblemState(
        version=1,
        goal="size a doublet",
        results=(Result(id="r1", summary="a simulation", reference="result/abc"),),
        assumptions=(Assumption(id="a1", text="return temperature 40 C"),),
        questions=(Question(id="q1", text="Which site?"),),
    )
    llm = Metered(looking(12))
    result, events = await drive(
        llm, context(problem=problem), hooks=[CostBudget(0.05, prices=PRICES), TimeLimit(1e9)]
    )
    answer = result.answer
    assert result.stop_reason == "denied" and result.status == "failed"
    assert "Asked: size a doublet" in answer and "r1: a simulation (result/abc)" in answer
    assert "a1: return temperature 40 C" in answer and "q1: Which site?" in answer
    assert "Why it stopped: cost budget" in answer
    assert "ask the user the open questions" in answer
    assert of_type(events, "run.finished")[-1].answer == answer


class Seen(Callback):
    """Collect the streamed text."""

    def __init__(self):
        """Start empty."""
        self.text = []

    def on_text(self, engine, event):
        """Keep a piece."""
        self.text.append(event.text)


async def test_the_partial_answer_streams_like_an_answer():
    """Callbacks see the text and the end of the run, as for an answer a model wrote."""

    seen = Seen()
    result, _ = await drive(
        Metered(looking(12)), hooks=[CostBudget(0.05, prices=PRICES)], callbacks=[seen]
    )
    assert "".join(seen.text) == result.answer


async def test_the_step_limit_answers_from_the_record_with_no_model_call():
    """Two steps allowed: two calls, no third for the answer."""
    llm = Metered(looking(5))
    result, _ = await drive(llm, max_steps=2)
    assert (result.stop_reason, llm.calls) == ("step_limit", 2)
    assert "Why it stopped: stopped after 2 steps" in result.answer


async def test_the_time_limit_answers_from_the_record():
    """The clock passes the limit after the first call."""
    ticks = iter([0.0, 0.0, 99.0, 99.0, 99.0])
    llm = Metered(looking(5))
    result, _ = await drive(llm, hooks=[TimeLimit(10, clock=lambda: next(ticks))])
    assert (result.stop_reason, llm.calls) == ("denied", 1)
    assert "Why it stopped: time limit: 99 s of 10 s" in result.answer


class Refuse(Hook):
    """Deny every LLM call, as a policy and not as a limit."""

    def before_llm_call(self, context, agent, messages):
        """Deny the call."""
        return Deny(reason="no")


async def test_a_denial_that_is_no_limit_has_no_partial_answer():
    """Only a budget or time limit answers from the record."""
    result, _ = await drive(Metered(looking(2)), hooks=[Refuse()])
    assert result.answer is None


async def test_the_answer_reserve_is_held_back_from_other_agents():
    """Calls of other agents stop at cap minus reserve; the answer agent may spend it."""
    held = CostBudget(0.2, answer_reserve=0.2, answer_agents=["explainer"], prices=PRICES)
    result, _ = await drive(Metered([says("x")]), hooks=[held])
    assert result.stop_reason == "denied"
    freed = CostBudget(0.2, answer_reserve=0.2, answer_agents=["worker"], prices=PRICES)
    result, _ = await drive(Metered([says("x")]), hooks=[freed])
    assert result.answer == "x"


def test_a_reserve_needs_the_agents_that_spend_it_and_is_off_when_unset():
    """No default: a reserve alone is refused; none is held without it."""
    with pytest.raises(BudgetError):
        CostBudget(1.0, answer_reserve=0.1)
    assert CostBudget(1.0).answer_reserve is None


def test_a_project_reserve_needs_one_cap():
    """A reserve has one unit."""
    with pytest.raises(BudgetError):
        ProjectBudget(MemoryUsageLedger(), "p", 10, 1.0, answer_reserve=1, answer_agents=["x"])


class Threaded(MemoryUsageLedger):
    """Remember the thread each read ran in."""

    def __init__(self):
        """Start with no reads."""
        super().__init__()
        self.threads = []

    def spent(self, project_id):
        """Note the thread and spend nothing."""
        self.threads.append(threading.current_thread())
        return Usage()


async def test_the_project_ledger_is_read_off_the_event_loop():
    """The ledger is sync and may be a database, so the hook reads it in a worker thread."""
    ledger = Threaded()
    await drive(Metered([says("x")]), hooks=[ProjectBudget(ledger, "p", max_cost=1.0)])
    assert ledger.threads and threading.current_thread() not in ledger.threads


async def test_a_project_cap_fits_calls_too():
    """The project cap lowers max_tokens like the run cap."""
    llm = Metered(looking(8))
    budget = ProjectBudget(MemoryUsageLedger(), "p", max_cost=CAP, prices=PRICES)
    result, events = await drive(llm, hooks=[budget])
    assert result.stop_reason == "denied" and spent(events) <= CAP


class Reply(BaseModel):
    """A typed answer."""

    text: str


async def test_a_typed_answer_gets_no_partial_text():
    """An agent whose output is not text keeps its answer empty at a stop."""
    agent = Worker()
    object.__setattr__(agent, "output", Output(Reply))
    result, _ = await drive(Metered(looking(4)), agent=agent, max_steps=1)
    assert (result.stop_reason, result.answer) == ("step_limit", None)
