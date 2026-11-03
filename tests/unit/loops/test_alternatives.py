"""``CompareLoop``: one designer run per family, verified one by one, compared and explained."""

import asyncio
import json

import pytest

from geomind.agents import Designer, Verifier
from geomind.context import ProblemState
from geomind.engine import Engine
from geomind.engine.hooks import TokenBudget
from geomind.engine.permissions import Permissions
from geomind.engine.recovery import recover
from geomind.export import render_export
from geomind.loops import CompareLoop
from geomind.loops.compare import alternatives_table, family_task, plan_instructions
from geomind.providers.fake import FakeLLM
from geomind.types import Completion, ToolCall, Usage
from tests.fixtures.runs import context, engine_for, of_type, says, uses

CASE = {
    "time": {"start": "2030-01-01", "end": "2030-01-03", "step": {"value": 1, "unit": "d"}},
    "demand": {"heating": {"power": {"unit": "MW", "file": "demand.csv", "column": "heat"}}},
}
PASSED = {"passed": True, "checks": [], "failures": []}
FAILED = {
    "passed": False,
    "checks": [],
    "failures": [{"name": "unmet", "domain": "sizing", "detail": "2 MW against 0 MW"}],
}
FAMILIES = [
    {"id": "alpha", "summary": "one doublet", "status": "open"},
    {"id": "beta", "summary": "two doublets", "status": "open"},
    {"id": "gamma", "summary": "a heat pump", "status": "open"},
]
USAGE = Usage(input_tokens=10, output_tokens=10, cost=0.0)


def update(call_id, *changes):
    """Return a completion that writes the state."""
    return uses(ToolCall(id=call_id, name="update_state", input={"changes": list(changes)}))


def plan(families=FAMILIES):
    """Return the planning designer's completions: record the families, hand over."""
    record = {"op": "add", "path": "/design/families", "value": families}
    search = {"op": "add", "path": "/design/search", "value": {"objective": "lcts"}}
    return [update("p1", record, search), says("planned")]


def entry(family, verdict="feasible", reason=None):
    """Return the alternative a family run records."""
    return {
        "family": family,
        "design": f"design/{family}_best",
        "result": f"result/{family}",
        "verdict": verdict,
        "reason": reason,
    }


def family_run(family, verdict="feasible", reason=None):
    """Return one family run's completions: add its entry, hand over."""
    add = {"op": "add", "path": "/design/alternatives/-", "value": entry(family, verdict, reason)}
    return [update(f"f-{family}", add), says(f"{family} done")]


def verifier_run(family):
    """Return the verifier's completions: record the verification of one family."""
    record = {"op": "add", "path": "/verification", "value": {"result": f"result/{family}"}}
    return [update(f"v-{family}", record), says("checked")]


COMPARISON = {
    "by": ["lcts", "co2"],
    "ranking": [{"family": "beta", "rank": 1, "pareto": True}],
    "recommended": "beta",
}


def economist_run():
    """Return the economist's completions: record the comparison, hand over."""
    record = {"op": "add", "path": "/design/comparison", "value": COMPARISON}
    return [update("e1", record), says("compared")]


def script():
    """Return a sequential run on three families, the last one infeasible."""
    return [
        *plan(),
        *family_run("alpha"),
        *family_run("beta"),
        *family_run("gamma", "infeasible", "no trial met the cooling peak"),
        *verifier_run("alpha"),
        *verifier_run("beta"),
        *economist_run(),
        says("the comparison"),
    ]


@pytest.fixture
def verdicts(monkeypatch):
    """Let gemini pass every design, and the ``Verified`` hook too."""
    monkeypatch.setattr("geomind.loops.compare.verify_design", lambda _: PASSED)
    monkeypatch.setattr("geomind.engine.hooks.verify_design", lambda _: PASSED)


async def run_loop(completions, **options):
    """Run a compare loop on scripted completions; return result, engine and events."""
    concurrency = options.pop("concurrency", None)
    engine = engine_for(completions, **options)
    start = context("Compare alternatives for the case.", problem=ProblemState(case=CASE))
    loop = CompareLoop(Designer(), Verifier(), concurrency=concurrency)
    result = await loop.run(engine, start)
    return result, engine, engine.store.load_events(start.run_id)


def alternatives(events):
    """Return the alternatives of the final state of a log."""
    return recover(events).problem.design["alternatives"]


def agents_of(events):
    """Return the agents the loop ran, in order."""
    return [event.agent for event in of_type(events, "run.started")][1:]


async def test_each_family_gets_its_own_designer_run(verdicts):
    """A plan, one family run each, one verifier each feasible design, then the rest."""
    result, _, events = await run_loop(script())
    assert result.status == "done"
    assert agents_of(events) == [
        "designer",
        "family_designer",
        "family_designer",
        "family_designer",
        "verifier",
        "verifier",
        "economist",
        "explainer",
    ]


async def test_an_infeasible_family_keeps_its_reason_and_does_not_stop_the_others(verdicts):
    """Two are verified, and the third stays in the table with why."""
    _, _, events = await run_loop(script())
    verdict = {item["family"]: item["verdict"] for item in alternatives(events)}
    assert verdict == {"alpha": "verified", "beta": "verified", "gamma": "infeasible"}
    gamma = next(item for item in alternatives(events) if item["family"] == "gamma")
    assert gamma["reason"] == "no trial met the cooling peak"


async def test_a_family_that_gemini_rejects_is_kept_with_the_failures(monkeypatch):
    """The verifier's gate is gemini's: a failed design is rejected, the others stay."""
    verdict = {"design/alpha_best": FAILED}

    def verify(found):
        return verdict.get(found.problem.design["reference"], PASSED)

    monkeypatch.setattr("geomind.loops.compare.verify_design", verify)
    monkeypatch.setattr("geomind.engine.hooks.verify_design", lambda _: PASSED)
    _, _, events = await run_loop(script())
    alpha = next(item for item in alternatives(events) if item["family"] == "alpha")
    assert alpha["verdict"] == "rejected" and "unmet" in alpha["reason"]


async def test_a_family_run_that_fails_is_recorded_and_the_others_go_on(verdicts):
    """A run that records nothing gets an entry with the reason, and the loop goes on."""
    completions = script()
    completions[2:4] = [says("I could not build it")]
    _, _, events = await run_loop(completions)
    alpha = next(item for item in alternatives(events) if item["family"] == "alpha")
    assert alpha["verdict"] == "failed" and "could not build" in alpha["reason"]
    assert {item["family"] for item in alternatives(events)} == {"alpha", "beta", "gamma"}


async def test_a_blocked_family_is_in_the_table_without_a_run(verdicts):
    """A family gemini cannot build is reported, with no designer run."""
    blocked = {"id": "delta", "summary": "needs a missing model", "status": "blocked"}
    completions = script()
    completions[:2] = plan([*FAMILIES, blocked])
    _, _, events = await run_loop(completions)
    delta = next(item for item in alternatives(events) if item["family"] == "delta")
    assert delta["verdict"] == "blocked" and delta["reason"] == "needs a missing model"
    assert agents_of(events).count("family_designer") == 3


async def test_the_recommended_design_is_the_final_one(verdicts):
    """The state ends on the economist's recommendation, verified by the ``Verified`` hook."""
    _, _, events = await run_loop(script())
    problem = recover(events).problem
    assert problem.design["reference"] == "design/beta_best"
    assert problem.verification["result"] == "result/beta"


async def test_the_table_reaches_the_explainer_and_the_export(verdicts):
    """Every family, feasible or not, is in the explainer's task and in the export."""
    result, _, events = await run_loop(script())
    task = next(e for e in of_type(events, "run.started") if e.agent == "explainer")
    assert "no trial met the cooling peak" in task.messages[0].content
    assert "beta" in task.messages[0].content and "Pareto" in task.messages[0].content
    export = render_export(events)
    assert "## Comparison" in export
    assert "| gamma | infeasible |" in export
    assert "stop: compared" in result.answer


async def test_no_verified_design_still_explains_the_table(monkeypatch):
    """With nothing verified the answer says so, and no design reaches the user."""
    monkeypatch.setattr("geomind.loops.compare.verify_design", lambda _: FAILED)
    monkeypatch.setattr("geomind.engine.hooks.verify_design", lambda _: FAILED)
    completions = [*script()[:-3], says("nothing passed")]
    result, _, events = await run_loop(completions)
    assert result.status == "done"
    assert "stop: no_verified" in result.answer
    assert "economist" not in agents_of(events)
    assert "reference" not in recover(events).problem.design


async def test_no_families_stops_with_a_clear_answer(verdicts):
    """A designer that records no family ends the comparison, naming the reason."""
    result, _, events = await run_loop([says("nothing to compare")])
    assert "stop: no_alternatives" in result.answer
    assert "family_designer" not in agents_of(events)


class ByTask(FakeLLM):
    """Answer by the run's task, so a parallel run gets the same script in any order."""

    def __init__(self, scripts):
        """Keep the completions of each family and of the rest, in order."""
        super().__init__([])
        self.scripts = {key: list(value) for key, value in scripts.items()}
        self.active = 0
        self.most = 0

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Return the next completion of the first script the task names."""
        task = next(item.content for item in messages if item.role == "user")
        key = next(name for name in self.scripts if name != "rest" and f"only: {name}" in task)
        self.active += 1
        self.most = max(self.most, self.active)
        await asyncio.sleep(0.02)
        self.active -= 1
        return self.scripts[key].pop(0)


class Routed(FakeLLM):
    """Send a family run to ``ByTask``, and any other call down the plain script."""

    def __init__(self, rest, families):
        """Keep both scripts."""
        super().__init__(rest)
        self.families = ByTask(families)

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Answer from the script of the call."""
        task = next(item.content for item in messages if item.role == "user")
        if "Design one alternative only" in task:
            return await self.families.complete(messages, tools, model=model, settings=settings)
        return await super().complete(messages, tools, model=model, settings=settings)


def parallel_llm():
    """Return a provider for a parallel run of the three families."""
    rest = [*plan(), *verifier_run("alpha"), *verifier_run("beta"), *economist_run(), says("end")]
    families = {
        "alpha": family_run("alpha"),
        "beta": family_run("beta"),
        "gamma": family_run("gamma", "infeasible", "no trial met the cooling peak"),
    }
    return Routed(rest, families)


async def run_parallel(concurrency):
    """Run the families with ``concurrency``; return the result, engine, events and provider."""
    llm = parallel_llm()
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"))
    start = context("Compare alternatives for the case.", problem=ProblemState(case=CASE))
    loop = CompareLoop(Designer(), Verifier(), concurrency=concurrency)
    result = await loop.run(engine, start)
    return result, engine, engine.store.load_events(start.run_id), llm


async def test_families_run_side_by_side_up_to_the_limit(verdicts):
    """Three families at a limit of two: never more than two at a time, all three finish."""
    result, _, events, llm = await run_parallel(2)
    assert result.status == "done"
    assert llm.families.most == 2
    assert {item["family"] for item in alternatives(events)} == {"alpha", "beta", "gamma"}


async def test_unset_concurrency_is_sequential(verdicts):
    """No limit in the settings means one family at a time."""
    _, _, _, llm = await run_parallel(None)
    assert llm.families.most == 1


async def test_parallel_usage_adds_up(verdicts):
    """Every nested run's usage reaches the root, however the runs interleave."""
    result, _, events, _ = await run_parallel(3)
    calls = [event for event in events if event.type == "llm.completed"]
    assert result.usage.input_tokens == sum(e.completion.usage.input_tokens for e in calls)


async def test_a_sequential_run_replays(verdicts):
    """The new driver's moves come back from its log."""
    result, engine, _ = await run_loop(script())
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.status, replayed.answer) == (result.status, result.answer)


async def test_a_parallel_run_replays(verdicts):
    """The nested runs are matched to their calls by step and task, whatever order they ended."""
    result, engine, _, _ = await run_parallel(3)
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.status, replayed.answer) == (result.status, result.answer)


async def test_a_new_loop_resumes_with_the_recorded_settings():
    """The logged limit and mode come back, as ``load_state_dict`` promises."""
    loop = CompareLoop(Designer(), Verifier())
    loop.load_state_dict({"max_rounds": 2, "concurrency": 3, "asks": True})
    assert (loop.max_rounds, loop.concurrency, loop.asks) == (2, 3, True)


def test_the_plan_of_an_auto_run_records_assumptions_and_asks_nothing():
    """In auto mode nobody can answer, so proposed families are unconfirmed assumptions."""
    task = plan_instructions(asks=False)
    assert "confirmed: false" in task and "ask_user" not in task


def test_the_plan_of_an_interactive_run_confirms_with_the_user():
    """With a user there, proposed families are confirmed first."""
    assert "ask_user" in plan_instructions(asks=True)


def test_no_hard_coded_count_of_families():
    """The number of alternatives is the request's or the case's."""
    assert "two or three" not in plan_instructions(asks=False)


def test_a_family_task_keeps_the_run_to_its_own_family():
    """Names, state and scope are the family's own."""
    task = family_task("Compare.", FAMILIES[0])
    assert "only: alpha" in task and "alpha_" in task and "/design/alternatives/-" in task


async def test_an_interactive_mode_runs_one_family_at_a_time(verdicts):
    """A permission question needs one pending run, so ``ask`` ignores the limit."""
    engine = engine_for(script())
    engine.permissions = Permissions(mode="ask", allow=("*",))
    loop = CompareLoop(Designer(), Verifier(), concurrency=3)
    loop.guard(engine)
    assert loop.agent.batch_size() == 1


async def test_a_budget_stop_lists_the_finished_alternatives(verdicts):
    """The cap covers the whole loop, and the partial answer names what finished."""
    usage = Usage(input_tokens=100, output_tokens=0, cost=0.0)
    completions = [
        Completion(text=item.text, tool_calls=item.tool_calls, usage=usage, model="fake/model")
        for item in script()
    ]
    result, _, events = await run_loop(completions, hooks=[TokenBudget(500)])
    assert result.status != "done" or "partial" in result.answer
    assert "alpha" in result.answer
    assert "family_designer" in agents_of(events)


async def test_runs_side_by_side_share_the_cap(verdicts):
    """A sibling still running counts: a cap below one family's cost stops the batch."""
    llm = parallel_llm()
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"), hooks=[TokenBudget(30)])
    start = context("Compare alternatives for the case.", problem=ProblemState(case=CASE))
    result = await CompareLoop(Designer(), Verifier(), concurrency=3).run(engine, start)
    events = engine.store.load_events(start.run_id)
    assert "partial" in result.answer
    assert sum(event.type == "llm.completed" for event in events) < 5


class Metered(Routed):
    """Charge every call a fixed usage, its output cut to the call's ``max_tokens``."""

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Answer as ``Routed``, charging the input bound and up to 40 output tokens."""
        completion = await super().complete(messages, tools, model=model, settings=settings)
        text = "".join(message.model_dump_json() for message in messages) + json.dumps(tools)
        output = min(40, settings.get("max_tokens") or 40)
        usage = Usage(input_tokens=len(text) // 2, output_tokens=output, cost=0.0)
        return completion.model_copy(update={"usage": usage})


@pytest.mark.parametrize("cap", [60_000, 80_000, 100_000])
async def test_runs_side_by_side_never_end_above_the_cap(verdicts, cap):
    """Each call holds its worst case until it returns, so calls in flight cannot pass the cap."""
    plain = parallel_llm()
    llm = Metered(plain.completions, plain.families.scripts)
    budget = TokenBudget(cap, bound_input=True)
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"), hooks=[budget])
    start = context("Compare alternatives for the case.", problem=ProblemState(case=CASE))
    result = await CompareLoop(Designer(), Verifier(), concurrency=3).run(engine, start)
    events = engine.store.load_events(start.run_id)
    assert result.usage.input_tokens + result.usage.output_tokens <= cap
    assert sum(event.type == "llm.completed" for event in events) > 2


def retried_script():
    """Return a run whose first alpha design gemini rejects and whose second passes."""
    return [
        *plan(),
        *family_run("alpha"),
        *family_run("beta"),
        *family_run("gamma", "infeasible", "no trial met the cooling peak"),
        *verifier_run("alpha"),
        *family_run("alpha"),
        *verifier_run("beta"),
        *verifier_run("alpha"),
        *economist_run(),
        says("the comparison"),
    ]


def rejecting_once(monkeypatch):
    """Let gemini reject the first check of alpha and pass every other one."""
    seen = []

    def verify(found):
        reference = found.problem.design["reference"]
        seen.append(reference)
        return (
            FAILED
            if seen.count("design/alpha_best") == 1 and reference.startswith("design/alpha")
            else PASSED
        )

    monkeypatch.setattr("geomind.loops.compare.verify_design", verify)
    monkeypatch.setattr("geomind.engine.hooks.verify_design", lambda _: PASSED)


async def test_a_rejected_family_is_designed_again_with_the_verifier_s_reason(monkeypatch):
    """With one retry, alpha runs again, told why it failed, and passes."""
    rejecting_once(monkeypatch)
    engine = engine_for(retried_script())
    start = context("Compare alternatives for the case.", problem=ProblemState(case=CASE))
    result = await CompareLoop(Designer(), Verifier(), retries=1).run(engine, start)
    events = engine.store.load_events(start.run_id)
    tasks = [
        e.messages[0].content
        for e in of_type(events, "run.started")
        if e.agent == "family_designer"
    ]
    assert len(tasks) == 4 and "unmet: 2 MW against 0 MW" in tasks[3]
    assert "alpha_r1_" in tasks[3]
    verdict = {item["family"]: item["verdict"] for item in alternatives(events)}
    assert verdict["alpha"] == "verified" and result.status == "done"


async def test_without_retries_a_rejected_family_stays_rejected(monkeypatch):
    """No setting, no retry: the reason stays in the table."""
    rejecting_once(monkeypatch)
    completions = [*retried_script()[:10], *retried_script()[12:]]
    _, _, events = await run_loop(completions)
    tasks = [e for e in of_type(events, "run.started") if e.agent == "family_designer"]
    assert len(tasks) == 3
    alpha = next(item for item in alternatives(events) if item["family"] == "alpha")
    assert alpha["verdict"] == "rejected"


async def test_retries_are_bounded(monkeypatch):
    """A family rejected every time runs once more per retry, then stays rejected."""
    monkeypatch.setattr(
        "geomind.loops.compare.verify_design",
        lambda found: (
            FAILED if found.problem.design["reference"].startswith("design/alpha") else PASSED
        ),
    )
    monkeypatch.setattr("geomind.engine.hooks.verify_design", lambda _: PASSED)
    engine = engine_for(retried_script())
    start = context("Compare alternatives for the case.", problem=ProblemState(case=CASE))
    await CompareLoop(Designer(), Verifier(), retries=1).run(engine, start)
    events = engine.store.load_events(start.run_id)
    assert sum(e.agent == "family_designer" for e in of_type(events, "run.started")) == 4
    alpha = next(item for item in alternatives(events) if item["family"] == "alpha")
    assert alpha["verdict"] == "rejected"


def test_the_retries_come_from_the_settings(monkeypatch):
    """``compare_retries`` gives the limit when the loop is given none."""
    from geomind import runtime

    with runtime.settings(compare_retries=2):
        assert CompareLoop(Designer(), Verifier()).retries == 2
    assert CompareLoop(Designer(), Verifier()).retries is None


def test_the_table_has_a_row_for_every_family():
    """Verdict and reason come straight from the state; a missing value stays empty."""
    table = alternatives_table({"alternatives": [entry("alpha", "verified"), {"family": "b"}]})
    assert "| alpha | verified | design/alpha_best | result/alpha |  |" in table
    assert "| b |  |  |  |  |" in table


def test_an_old_state_has_no_table():
    """Entries without a verdict are the old form, which the export leaves as it was."""
    assert alternatives_table({"alternatives": [{"family": "a", "design": "design/a"}]}) == ""
    assert json.dumps(alternatives_table({})) == '""'
