"""Usage and context per session and per agent (contract 0.4.24, additions only).

A session is one run of one agent: the root run, or a nested run per delegation. Each session
holds its own model calls only, so a root's ``sessions`` add up to ``total``, which equals the last
``usage`` event and ``RunResult.usage``: every call counted once.
"""

from pathlib import Path

import pytest

from geomind import runtime
from geomind.engine import Engine, Permissions
from geomind.providers import FakeLLM
from geomind.stores import FileRunStore, MemoryWorkspace
from geomind.stores.usage import usage_report
from geomind.types import Usage
from tests.fixtures.runs import EXECUTED, Lead, call, context, of_type, says, uses

OLD_LOG = Path(__file__).parents[2] / "fixtures" / "logs" / "mcp_0_4_22_dev41"
ROOT_CALLS = (
    Usage(input_tokens=100, output_tokens=10, cost=0.1, cached_tokens=60),
    Usage(input_tokens=150, output_tokens=15, cost=0.15, cached_tokens=100),
    Usage(input_tokens=200, output_tokens=20, cost=0.2, cached_tokens=150),
)
FIRST_HELPER = (
    Usage(input_tokens=20, output_tokens=2, cost=0.02, cached_tokens=5),
    Usage(input_tokens=30, output_tokens=3, cost=0.03, cached_tokens=10),
)
SECOND_HELPER = Usage(input_tokens=7, output_tokens=1, cost=0.007)
NEW_FIELDS = {
    "step.started": ("session", "context_window"),
    "step.finished": ("context",),
    "run.finished": ("sessions", "agents", "total"),
}
"""The fields 0.4.24 added: a log before it has none of them."""


@pytest.fixture(autouse=True)
def clean_run():
    """Forget executed tools; no retry waits."""
    EXECUTED.clear()
    with runtime.settings(retry_delay=0):
        yield


def script():
    """Return the completions of a lead that delegates to its helper twice.

    The first helper session takes two steps (a lookup, then its answer), the second one step.
    """
    first, second, last = ROOT_CALLS
    return [
        uses(call("helper", "d1", task="find it"), usage=first),
        uses(call("lookup", "n1", key="k"), usage=FIRST_HELPER[0]),
        says("found", usage=FIRST_HELPER[1]),
        uses(call("helper", "d2", task="find more"), usage=second),
        says("more", usage=SECOND_HELPER),
        says("end", usage=last),
    ]


async def two_delegations(store=None):
    """Run the lead; return ``(result, engine, events)``."""
    options = {"store": store} if store is not None else {}
    engine = Engine(llm=FakeLLM(script()), permissions=Permissions(mode="auto"), **options)
    start = context("lead the work")
    result = await engine.run(Lead(), start)
    return result, engine, engine.store.load_events(start.run_id)


def added(usages):
    """Return the sum of usages."""
    return sum(usages, Usage())


def tokens(usage):
    """Return the token counts of a usage, which add up exactly."""
    return (usage.input_tokens, usage.output_tokens, usage.cached_tokens)


async def test_each_session_holds_its_own_calls_and_one_agent_groups_its_two_sessions():
    """Two delegations of one agent are two sessions; the lead's holds no helper call."""
    result, _, events = await two_delegations()
    window = int(runtime.get("context_window"))
    root, first, second = result.sessions
    helper_runs = [e.run_id for e in of_type(events, "run.started") if e.parent is not None]
    assert [s.session for s in result.sessions] == [result.run_id, *helper_runs]
    assert [s.agent for s in result.sessions] == ["lead", "lead.helper_agent", "lead.helper_agent"]
    assert [s.parent for s in result.sessions] == [None, result.run_id, result.run_id]
    assert {s.model for s in result.sessions} == {"fake/model"}
    assert tokens(root.usage) == tokens(added(ROOT_CALLS))
    assert tokens(first.usage) == tokens(added(FIRST_HELPER))
    assert tokens(second.usage) == tokens(SECOND_HELPER)
    assert root.usage.cost == pytest.approx(0.45)
    assert [(s.steps, s.tool_calls) for s in result.sessions] == [(3, 2), (2, 1), (1, 0)]
    assert (root.context.peak_used, root.context.last_used, root.context.window) == (
        200,
        200,
        window,
    )
    lead, helper = result.agents
    assert (lead.agent, lead.sessions, lead.steps, lead.tool_calls) == ("lead", 1, 3, 2)
    assert (helper.agent, helper.sessions, helper.steps, helper.tool_calls) == (
        "lead.helper_agent",
        2,
        3,
        1,
    )
    assert tokens(helper.usage) == tokens(added([*FIRST_HELPER, SECOND_HELPER]))


async def test_the_total_counts_each_call_once_and_equals_the_last_usage_event_and_the_result():
    """Sum of sessions == every completion of the log == last ``usage`` == ``RunResult.usage``."""
    result, _, events = await two_delegations()
    every = added([*ROOT_CALLS, *FIRST_HELPER, SECOND_HELPER])
    total = result.total
    assert (total.input_tokens, total.output_tokens, total.cached_tokens) == tokens(every)
    assert (total.steps, total.tool_calls) == (6, 3)
    assert total.cost == pytest.approx(every.cost)
    sessions = added([s.usage for s in result.sessions])
    assert tokens(sessions) == tokens(every)
    last = of_type(events, "usage")[-1]
    assert (last.input_tokens, last.output_tokens) == (total.input_tokens, total.output_tokens)
    assert last.cost == pytest.approx(total.cost)
    assert (result.usage.input_tokens, result.usage.output_tokens) == (
        total.input_tokens,
        total.output_tokens,
    )
    assert result.usage.cost == pytest.approx(total.cost)
    finished = of_type(events, "run.finished")
    root_end = next(e for e in finished if e.parent is None)
    assert root_end.sessions == result.sessions and root_end.total == result.total
    assert root_end.agents == result.agents
    nested_ends = [e for e in finished if e.parent is not None]
    assert len(nested_ends) == 2
    assert all(e.sessions is None and e.agents is None and e.total is None for e in nested_ends)
    data = root_end.data()
    assert data["total"]["cached_tokens"] == every.cached_tokens
    assert [item["session"] for item in data["sessions"]] == [s.session for s in result.sessions]


async def test_step_finished_usage_is_the_one_call_of_the_step():
    """A step that delegated reports its own call, not what its nested run spent."""
    _, _, events = await two_delegations()
    calls = {(e.run_id, e.index): e.completion.usage for e in of_type(events, "llm.completed")}
    steps = of_type(events, "step.finished")
    assert len(steps) == 6
    for step in steps:
        assert step.usage == calls[(step.run_id, step.index)]
    root_steps = [e for e in steps if e.parent is None]
    assert [e.usage.input_tokens for e in root_steps] == [100, 150, 200]
    assert root_steps[0].data()["usage"] == {
        "input_tokens": 100,
        "output_tokens": 10,
        "cached_tokens": 60,
        "cost": 0.1,
    }
    window = int(runtime.get("context_window"))
    for step in steps:
        used = calls[(step.run_id, step.index)].input_tokens
        assert (step.context.used, step.context.window, step.context.remaining) == (
            used,
            window,
            window - used,
        )
    started = of_type(events, "step.started")
    assert all(e.session == e.run_id and e.context_window == window for e in started)


async def test_a_new_session_of_the_same_agent_starts_from_its_own_messages():
    """The second helper session sends its task only; its context excludes the first session."""
    _, engine, events = await two_delegations()
    sent = engine.llm.llm.calls[4]["messages"]
    contents = [message.content for message in sent]
    assert "find more" in contents
    assert not {"find it", "found", "lead the work"} & set(contents)
    helper_runs = [e.run_id for e in of_type(events, "run.started") if e.parent is not None]
    second = [e for e in of_type(events, "step.finished") if e.run_id == helper_runs[1]]
    assert second[0].context.used == SECOND_HELPER.input_tokens
    report, _, _ = usage_report(events)
    assert (report[2].context.peak_used, report[2].context.last_used) == (7, 7)
    assert report[1].context.last_used == 30


def strip_new_fields(path):
    """Rewrite a stored log as a version before 0.4.24 left it: without the added fields."""
    import json

    lines = []
    for line in path.read_text().splitlines():
        data = json.loads(line)
        for name in NEW_FIELDS.get(data["type"], ()):
            data.pop(name, None)
        lines.append(json.dumps(data))
    path.write_text("\n".join(lines) + "\n")


async def test_a_log_without_the_fields_loads_reports_and_replays(tmp_path):
    """An older log loads with the fields absent, and its replay reports them."""
    result, _, _ = await two_delegations(FileRunStore(tmp_path))
    strip_new_fields(tmp_path / result.run_id / "events.jsonl")
    store = FileRunStore(tmp_path)
    events = store.load_events(result.run_id)
    started = of_type(events, "step.started")
    assert all(e.session is None and e.context_window is None for e in started)
    assert all(e.context is None for e in of_type(events, "step.finished"))
    assert all(e.sessions is None for e in of_type(events, "run.finished"))
    assert all("context" not in e.data() for e in of_type(events, "step.finished"))
    sessions, _, total = usage_report(events)
    assert [s.context.window for s in sessions] == [None, None, None]
    assert total.input_tokens == result.total.input_tokens
    replayed_events = []
    replayed = await Engine.replay(store, result.run_id, replayed=replayed_events)
    assert replayed.answer == "end"
    assert tokens(replayed.total) == tokens(result.total)
    assert [s.agent for s in replayed.sessions] == [s.agent for s in result.sessions]


async def test_a_log_of_0_4_22_loads_and_replays_with_the_report():
    """The stored 0.4.22.dev41 run has none of the fields and still replays."""
    store = FileRunStore(OLD_LOG)
    [run_id] = [path.name for path in OLD_LOG.iterdir()]
    events = store.load_events(run_id)
    assert all(e.sessions is None for e in of_type(events, "run.finished"))
    every = added([e.completion.usage for e in events if e.type in ("llm.completed", "compaction")])
    _, _, total = usage_report(events)
    assert total.input_tokens == every.input_tokens
    replayed = await Engine.replay(store, run_id, workspace=MemoryWorkspace())
    assert replayed.total is not None and replayed.sessions[0].session == replayed.run_id
