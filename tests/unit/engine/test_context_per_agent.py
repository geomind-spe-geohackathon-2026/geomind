"""Context and steps are each agent's own; only a budget counts the whole tree of runs.

Sahand (2026-11-04): the context limit is computed for each agent and its own session, never for
the run and its nested runs, whose ``usage`` includes what the children spent.
"""

import geomind as gd
from geomind import runtime
from geomind.engine import Context, Engine, Permissions
from geomind.engine.hooks import TokenBudget
from geomind.providers import FakeLLM
from geomind.tools import Delegate
from geomind.types import Message, Usage
from tests.fixtures.runs import Lead, Worker, call, of_type, says, uses

WINDOW = 100_000
HUGE = Usage(input_tokens=10_000_000, output_tokens=1_000_000)
"""Far past any window: what a nested run's calls may add up to."""


class SettingsLLM(FakeLLM):
    """A scripted provider that also keeps the settings of each call."""

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Keep the settings, then answer from the script."""
        completion = await super().complete(
            messages, tools, model=model, settings=settings, on_text=on_text
        )
        self.calls[-1]["settings"] = settings
        return completion


def chat(turns):
    """Return a short history of ``turns`` turns."""
    messages = []
    for number in range(turns):
        messages.append(Message(role="user", content=f"question {number}"))
        messages.append(Message(role="assistant", content=f"answer {number}"))
    return [*messages, Message(role="user", content="now")]


async def run_lead(script, agent=None, hooks=(), max_steps=None):
    """Run a lead over a short history; return ``(result, llm, events)``."""
    llm = SettingsLLM(script)
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"), hooks=list(hooks))
    start = Context(messages=chat(9))
    result = await engine.run(agent or Lead(), start, max_steps=max_steps)
    return result, llm, engine.store.load_events(start.run_id)


def compactions(events, run_id):
    """Return the compaction events of one run."""
    return [event for event in of_type(events, "compaction") if event.run_id == run_id]


async def test_a_parent_does_not_compact_on_its_children_s_tokens():
    """Its nested run used far more than the window; the parent's own conversation is short."""
    script = [
        uses(call("helper", task="t")),
        uses(call("lookup", key="k"), usage=HUGE),
        says("found", usage=HUGE),
        says("end"),
    ]
    with runtime.settings(context_window=WINDOW, compaction_keep_turns=2):
        result, llm, events = await run_lead(script)
    assert result.status == "done" and result.answer == "end"
    assert result.usage.input_tokens > WINDOW
    assert of_type(events, "compaction") == []
    assert llm.calls[-1]["settings"]["max_tokens"] == runtime.get("max_output_tokens")


async def test_a_nested_agent_compacts_on_its_own_context_only():
    """The child's own last call passed the threshold: it compacts; its parent does not."""
    script = [
        uses(call("helper", task="t")),
        uses(call("lookup", key="k"), usage=Usage(input_tokens=int(0.7 * WINDOW))),
        says("summary of the child"),
        says("found"),
        says("end"),
    ]
    with runtime.settings(context_window=WINDOW, compaction_keep_turns=0):
        result, llm, events = await run_lead(script)
    child = next(e.run_id for e in of_type(events, "run.started") if e.parent is not None)
    assert result.status == "done" and result.answer == "end"
    assert len(compactions(events, child)) == 1
    assert compactions(events, result.run_id) == []
    assert llm.calls[2]["model"] == runtime.get("summarizer_model")


async def test_the_window_check_uses_the_agent_s_own_last_call():
    """Short messages, a long last input: one summary, and the stale count does not ask again."""
    script = [
        uses(call("lookup", key="k"), usage=Usage(input_tokens=int(0.7 * WINDOW))),
        says("the summary"),
        uses(call("lookup", "c2", key="k")),
        says("done"),
    ]
    with runtime.settings(context_window=WINDOW, compaction_keep_turns=2):
        result, _, events = await run_lead(script, agent=Worker())
    assert result.status == "done"
    assert len(of_type(events, "compaction")) == 1
    llm_types = [e.type for e in events if e.type in ("compaction", "llm.completed")]
    assert llm_types == ["llm.completed", "compaction", "llm.completed", "llm.completed"]


async def test_a_budget_still_counts_the_whole_tree_of_runs():
    """``TokenBudget`` is a cost cap over the run and its nested runs, not a context limit."""
    script = [
        uses(call("helper", task="t"), usage=Usage(input_tokens=900)),
        uses(call("lookup", key="k")),
        says("found"),
        says("end"),
    ]
    result, _, events = await run_lead(script, hooks=[TokenBudget(910)])
    nested = [e for e in of_type(events, "run.finished") if e.parent is not None]
    assert nested[0].stop_reason == "denied"
    assert "token budget: used 915 of 910" in nested[0].message


async def test_a_nested_run_counts_its_own_steps_from_one():
    """A parent at a limit of 2 steps delegates to a child that takes 3 of its own."""
    script = [
        uses(call("helper", task="t")),
        uses(call("lookup", "l1", key="k")),
        uses(call("lookup", "l2", key="k")),
        says("found"),
        says("end"),
    ]
    result, _, events = await run_lead(script, max_steps=2)
    started = of_type(events, "run.started")
    finished = {e.run_id: e for e in of_type(events, "run.finished")}
    child = next(e for e in started if e.parent is not None)
    assert result.status == "done" and result.answer == "end" and result.steps == 2
    assert child.max_steps == runtime.get("max_steps")
    assert finished[child.run_id].stop_reason == "answer"
    assert of_type(events, "request") == []


async def test_each_delegation_gets_its_own_engineer_steps():
    """Two engineers in a row each take the whole ``engineer_max_steps``; none shares a count."""

    class Lead2(gd.Agent):
        """Delegates to a worker with its own step limit."""

        def __init__(self):
            super().__init__()
            self.helper = Delegate(Worker(), steps="engineer_max_steps")
            self.model = gd.Model("fake/model")

    engineer = [uses(call("lookup", "l", key="k")), says("found")]
    script = [
        uses(call("helper", "h1", task="one")),
        *engineer,
        uses(call("helper", "h2", task="two")),
        *engineer,
        says("end"),
    ]
    with runtime.settings(engineer_max_steps=2):
        result, _, events = await run_lead(script, agent=Lead2())
    nested = [e for e in of_type(events, "run.finished") if e.parent is not None]
    assert result.status == "done" and result.steps == 3
    assert [e.stop_reason for e in nested] == ["answer", "answer"]
    child_starts = [e for e in of_type(events, "run.started") if e.parent is not None]
    assert [e.max_steps for e in child_starts] == [2, 2]
