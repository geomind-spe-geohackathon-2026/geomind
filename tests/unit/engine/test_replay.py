"""Replay: offline, faithful, and honest about differences."""

import asyncio

import pytest

from geomind.agents import Agent, Model
from geomind.engine import Engine, Permissions
from geomind.engine.hooks import Hook, RequireApproval, TimeLimit, TokenBudget
from geomind.engine.replay import _nested_changes, version_differences
from geomind.engine.session import current_versions
from geomind.errors import ReplayError
from geomind.stores.run import MemoryRunStore
from geomind.tools import Delegate, tool, update_state
from geomind.types import Action, Deny, Message, ToolCall
from geomind.types.events import RunFinished, RunStarted, StateChanged, ToolRecorded, ToolStarted
from tests.fixtures.runs import (
    EXECUTED,
    Helper,
    Lead,
    Worker,
    call,
    context,
    engine_for,
    lookup,
    run,
    says,
    stopped_at_limit,
    uses,
)


class Rewriting(MemoryRunStore):
    """Change one recorded output, as a changed tool would."""

    def load_events(self, run_id):
        """Return the events with the output of the first tool changed."""
        events = super().load_events(run_id)
        for position, event in enumerate(events):
            if isinstance(event, ToolRecorded):
                events[position] = event.model_copy(update={"output": "other"})
                break
        return events


async def test_replay_passes_without_network():
    """A recorded run reruns from its log alone."""
    result, engine, _ = await run(
        [uses(call("lookup", key="k"), call("add", "c2", left=1, right=2)), says("end")]
    )
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.answer, replayed.steps) == ("end", 2)


async def test_a_call_id_reused_in_a_later_step_replays():
    """Ids are unique in one completion only: a later step may reuse one with another input."""
    result, engine, _ = await run(
        [uses(call("lookup", "c1", key="a")), uses(call("lookup", "c1", key="b")), says("end")]
    )
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.answer, replayed.steps) == ("end", 3)


async def test_read_and_compute_run_again_and_others_do_not():
    """Only pure tools execute in a replay."""
    result, engine, _ = await run(
        [uses(call("lookup", "a", key="k"), call("save_note", "b", text="x")), says("end")]
    )
    EXECUTED.clear()
    await Engine.replay(engine.store, result.run_id)
    assert EXECUTED == ["lookup"]


async def test_a_changed_result_names_the_step():
    """A different output of a pure tool is a mismatch at its step."""
    store = Rewriting()
    result, _, _ = await run([says("x")], store=store)
    result, engine, _ = await run([uses(call("lookup", key="k")), says("end")], store=store)
    with pytest.raises(ReplayError, match="step 1: tool lookup"):
        await Engine.replay(engine.store, result.run_id)


async def test_a_changed_answer_is_a_mismatch():
    """A recorded answer that does not come back is a mismatch."""
    result, engine, _ = await run([says("end")])
    events = engine.store.events[result.run_id]
    events[-1] = events[-1].model_copy(update={"answer": "other"})
    with pytest.raises(ReplayError, match="recorded answer 'other'"):
        await Engine.replay(engine.store, result.run_id)


async def test_a_denied_call_stays_denied():
    """A reused result keeps the original denial, though replay allows everything."""
    permissions = Permissions(deny=("save_note",))
    result, engine, _ = await run(
        [uses(call("save_note", text="x")), says("end")], permissions=permissions
    )
    EXECUTED.clear()
    assert (await Engine.replay(engine.store, result.run_id)).answer == "end"
    assert EXECUTED == []


async def test_a_refused_answer_is_refused_again():
    """The feedback of the original run comes back at its step."""

    class Once(Hook):
        refused = False

        def before_finish(self, context, agent, action):
            if self.refused:
                return None
            self.refused = True
            return Deny(reason="not yet")

    result, engine, _ = await run([says("first"), says("second")], hooks=[Once()])
    assert (await Engine.replay(engine.store, result.run_id)).answer == "second"


async def test_a_paused_run_never_runs_its_pending_tool():
    """A replay ends where the log ends, waiting on the same request."""
    result, engine, _ = await run(
        [uses(call("save_note", text="x"))], hooks=[RequireApproval(["save_note"])]
    )
    EXECUTED.clear()
    replayed = await Engine.replay(engine.store, result.run_id)
    assert EXECUTED == [] and replayed.status == "waiting"
    assert replayed.request.message == result.request.message


async def test_resumed_run_replays():
    """A question answered in the run is an answer in the replay."""
    engine = engine_for([uses(call("ask_user", question="q")), says("end")])
    start = context()
    paused = await engine.run(Worker(), start)
    await engine.resume(start.run_id, paused.request.id, {"text": "yes"})
    assert (await Engine.replay(engine.store, start.run_id)).answer == "end"


async def test_unknown_run_raises():
    """There is nothing to replay."""
    with pytest.raises(ReplayError, match="no recorded"):
        await Engine.replay(MemoryRunStore(), "nope")


class Ruled(Agent):
    """Looks a value up, then answers, by rule."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Tools
        self.lookup = lookup

    async def forward(self, context):
        """Call the tool once, then answer with its result."""
        results = [item.content for item in context.messages if item.role == "tool"]
        if results:
            return Action(text=f"found {results[0]}")
        return Action(tool_calls=(ToolCall(id="r1", name="lookup", input={"key": "k"}),))


async def test_a_rule_based_run_replays_without_a_model():
    """A rule step never calls the model, so the replay does not stop it."""
    result, engine, _ = await run([], agent=Ruled())
    replayed = await Engine.replay(engine.store, result.run_id)
    assert result.answer == "found value of k"
    assert (replayed.status, replayed.answer) == ("done", result.answer)


class Noting(Agent):
    """Records a goal in the problem state, then answers."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Tools
        self.update_state = update_state


class Reading(Agent):
    """Delegates to ``Noting``, then answers with the goal it recorded, by rule."""

    def __init__(self):
        """Declare the delegate."""
        super().__init__()

        # Tools
        self.noting = Delegate(Noting())

    async def forward(self, context):
        """Delegate once, then answer from the shared problem state."""
        if any(item.role == "tool" for item in context.messages):
            return Action(text=f"goal: {context.problem.goal}")
        return Action(tool_calls=(ToolCall(id="d1", name="noting", input={"task": "note"}),))


async def test_a_replay_keeps_the_state_changes_of_a_reused_nested_run():
    """A nested run is not run again, but what it wrote in the problem state is applied again."""
    goal = {"op": "replace", "path": "/goal", "value": "heat"}
    result, engine, _ = await run(
        [uses(call("update_state", changes=[goal])), says("ok")], agent=Reading()
    )
    replayed = await Engine.replay(engine.store, result.run_id)
    assert result.answer == "goal: heat"
    assert replayed.answer == "goal: heat"


@tool(effect="write")
async def keep(context, text: str):
    """Keep a text as an artifact."""
    await context.session.save_artifact("kept", text)
    return "kept"


class Keeping(Agent):
    """Keeps a text, then answers."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Tools
        self.keep = keep


class Loading(Agent):
    """Delegates to ``Keeping``, then answers with the artifact it kept, by rule."""

    def __init__(self):
        """Declare the delegate."""
        super().__init__()

        # Tools
        self.keeping = Delegate(Keeping())

    async def forward(self, context):
        """Delegate once, then answer from the run's artifacts."""
        if any(item.role == "tool" for item in context.messages):
            return Action(text=f"kept: {context.session.load_artifact('kept')}")
        return Action(tool_calls=(ToolCall(id="d1", name="keeping", input={"task": "keep"}),))


async def test_a_replay_reads_the_artifacts_of_the_recorded_run():
    """What a reused nested run saved is still there for the steps after it."""
    result, engine, _ = await run(
        [uses(call("keep", text="a design")), says("ok")], agent=Loading()
    )
    replayed = await Engine.replay(engine.store, result.run_id)
    assert replayed.answer == result.answer == "kept: a design"


DELAYS = {"first": 0.0, "second": 0.0, "third": 0.0}
"""Seconds each racing tool waits before it returns; a test sets them per run."""
VALUES = {"third": 3}


@tool(effect="compute")
async def first():
    """Return 1 after its delay."""
    await asyncio.sleep(DELAYS["first"])
    return 1


@tool(effect="compute")
async def second():
    """Return 2 after its delay."""
    await asyncio.sleep(DELAYS["second"])
    return 2


@tool(effect="compute")
async def third():
    """Return the third value after its delay."""
    await asyncio.sleep(DELAYS["third"])
    return VALUES["third"]


class Racer(Agent):
    """Calls three tools in one step."""

    def __init__(self):
        """Declare the racing tools."""
        super().__init__()

        # Tools
        self.first = first
        self.second = second
        self.third = third

        # Model
        self.model = Model("fake/model")


async def raced(order):
    """Run the three tools in one step, finishing in ``order``; return the result and engine."""
    DELAYS.update({name: 0.01 * position for position, name in enumerate(order)})
    step = uses(call("first", "r1"), call("second", "r2"), call("third", "r3"))
    return await run([step, says("end")], agent=Racer())


async def test_parallel_calls_replay_whatever_order_they_finish_in():
    """Calls of one step are matched by their place in the step, not by when they finish."""
    result, engine, _ = await raced(("first", "second", "third"))
    DELAYS.update({"first": 0.02, "second": 0.01, "third": 0.0})
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.answer, replayed.steps) == ("end", 2)


async def test_a_changed_output_of_a_parallel_call_still_fails():
    """A parallel call whose output differs is a mismatch, whatever the finishing order."""
    result, engine, _ = await raced(("third", "second", "first"))
    DELAYS.update({"first": 0.0, "second": 0.01, "third": 0.02})
    VALUES["third"] = 4
    try:
        with pytest.raises(ReplayError, match="step 1: tool third"):
            await Engine.replay(engine.store, result.run_id)
    finally:
        VALUES["third"] = 3


def delegated_log():
    """Return a log where two delegates of one step run at once and change the state in turn."""

    def started(run, task, sequence):
        return RunStarted(
            run_id=run,
            sequence=sequence,
            parent="root",
            run=run,
            root="root",
            agent_class="tests.Helper",
            max_steps=5,
            parent_step=1,
            messages=(Message(role="user", content=task),),
        )

    def changed(run, sequence, value):
        change = {"op": "replace", "path": "/design", "value": {"by": value}}
        return StateChanged(
            run_id=run, sequence=sequence, parent="root", version=sequence, changes=(change,)
        )

    return [
        ToolStarted(
            run_id="root", sequence=1, index=1, call_id="a", tool="helper", input={"task": "A"}
        ),
        ToolStarted(
            run_id="root", sequence=2, index=1, call_id="b", tool="helper", input={"task": "B"}
        ),
        started("child-a", "A", 3),
        started("child-b", "B", 4),
        changed("child-b", 5, "from b"),
        changed("child-a", 6, "from a"),
        ToolRecorded(run_id="root", sequence=7, index=1, call_id="b", tool="helper"),
        ToolRecorded(run_id="root", sequence=8, index=1, call_id="a", tool="helper"),
    ]


def test_parallel_delegates_keep_their_own_state_changes():
    """A nested run's state changes belong to the call that started it, not to every open call."""
    changes = _nested_changes(delegated_log(), "root")
    assert [change[0]["value"]["by"] for change in changes[(1, "a")]] == ["from a"]
    assert [change[0]["value"]["by"] for change in changes[(1, "b")]] == ["from b"]


async def replayed_log(engine, run_id):
    """Replay a run and return its result and the events of the replayed tree."""
    log = []
    result = await Engine.replay(engine.store, run_id, replayed=log)
    return result, log


def nested_ids(events):
    """Return the ids of the runs of a log that have a parent, in log order."""
    return [e.run_id for e in events if e.type == "run.started" and e.parent is not None]


async def test_a_nested_run_runs_again_with_its_own_completions():
    """The replayed log holds the nested run's completions and tool results."""
    script = [
        uses(call("helper", task="find")),
        uses(call("lookup", "n1", key="k")),
        says("found"),
        says("end"),
    ]
    result, engine, events = await run(script, agent=Lead())
    EXECUTED.clear()
    replayed, log = await replayed_log(engine, result.run_id)
    assert replayed.answer == "end"
    assert EXECUTED == ["lookup"]
    assert [
        (e.type, e.run_id, e.index) for e in log if e.type in ("llm.completed", "tool.result")
    ] == [(e.type, e.run_id, e.index) for e in events if e.type in ("llm.completed", "tool.result")]
    assert nested_ids(log) == nested_ids(events)


async def test_a_changed_completion_of_a_nested_run_names_that_run():
    """A nested run whose answer differs is a mismatch naming its run id and agent."""
    script = [uses(call("helper", task="find")), says("found"), says("end")]
    result, engine, events = await run(script, agent=Lead())
    nested = nested_ids(events)[0]
    stored = engine.store.events[result.run_id]
    for position, event in enumerate(stored):
        if event.type == "llm.completed" and event.run_id == nested:
            changed = event.completion.model_copy(update={"text": "other"})
            stored[position] = event.model_copy(update={"completion": changed})
    with pytest.raises(
        ReplayError, match=f"run {nested} \\(.*helper.*\\): .*recorded answer 'found'"
    ):
        await Engine.replay(engine.store, result.run_id)


async def test_delegates_of_one_step_replay_with_their_own_completions():
    """Two delegates of one step each get the completions of their own nested run."""
    script = [
        uses(call("helper", "d1", task="A"), call("helper", "d2", task="B")),
        says("answer A"),
        says("answer B"),
        says("end"),
    ]
    result, engine, events = await run(script, agent=Lead())
    replayed, log = await replayed_log(engine, result.run_id)
    answers = {e.run_id: e.answer for e in log if e.type == "run.finished"}
    recorded = {e.run_id: e.answer for e in events if e.type == "run.finished"}
    assert answers == recorded and replayed.answer == "end"


def test_nested_runs_are_matched_to_their_call_by_step_and_task():
    """Calls of one step keep their own nested run, whatever the order of the log."""
    from geomind.engine.replay import _children

    assert _children(delegated_log(), "root") == {(1, "a"): "child-a", (1, "b"): "child-b"}


class Middle(Agent):
    """Delegates to a helper."""

    def __init__(self):
        """Declare the delegate."""
        super().__init__()

        # Tools
        self.helper = Delegate(Helper())

        # Model
        self.model = Model("fake/model")


class Top(Agent):
    """Delegates to a middle agent."""

    def __init__(self):
        """Declare the delegate."""
        super().__init__()

        # Tools
        self.middle = Delegate(Middle())

        # Model
        self.model = Model("fake/model")


async def test_a_three_level_tree_replays_at_every_depth():
    """The deepest run's tool calls come back in the replayed log."""
    script = [
        uses(call("middle", task="m")),
        uses(call("helper", "h1", task="h")),
        uses(call("lookup", "l1", key="k")),
        says("deep"),
        says("middle done"),
        says("end"),
    ]
    result, engine, events = await run(script, agent=Top())
    EXECUTED.clear()
    replayed, log = await replayed_log(engine, result.run_id)
    assert replayed.answer == "end" and EXECUTED == ["lookup"]
    assert len(nested_ids(log)) == 2
    assert sum(e.type == "llm.completed" for e in log) == 6
    assert any(e.type == "tool.result" and e.tool == "lookup" for e in log)


async def test_a_stored_loop_shaped_recording_replays(tmp_path):
    """A log read back from a file, as a 0.3.0 run left it, replays its nested runs."""
    from geomind.stores.run import FileRunStore

    script = [
        uses(call("helper", task="find")),
        uses(call("lookup", key="k")),
        says("f"),
        says("e"),
    ]
    result, engine, _ = await run(script, agent=Lead(), store=FileRunStore(tmp_path))
    replayed, log = await replayed_log(Engine(store=FileRunStore(tmp_path)), result.run_id)
    assert replayed.answer == "e" and len(nested_ids(log)) == 1


async def test_a_replay_with_other_versions_reports_them_and_still_runs():
    """A recorded gemini version that differs is a report, never an error."""
    result, engine, _ = await run([says("end")])
    store = engine.store
    original = store.load_events(result.run_id)
    store.events[result.run_id] = [
        (
            e.model_copy(update={"versions": {**e.versions, "gemini": "0.0.1"}})
            if isinstance(e, RunStarted)
            else e
        )
        for e in original
    ]
    replayed = await Engine.replay(store, result.run_id)
    assert replayed.answer == "end"
    differences = version_differences(store.load_events(result.run_id))
    assert differences == {"gemini": ("0.0.1", current_versions()["gemini"])}


async def test_a_replay_of_a_log_without_versions_reports_no_difference():
    """A 0.3.0 log records no versions, so there is nothing to compare."""
    result, engine, events = await run([says("end")])
    stripped = [
        e.model_copy(update={"versions": {}}) if isinstance(e, RunStarted) else e for e in events
    ]
    assert version_differences(stripped) == {}


async def test_nested_runs_of_a_project_run_are_reused_without_a_workspace():
    """The log holds no project files, so without a workspace a nested run is not run again."""
    from geomind.stores import MemoryWorkspace

    engine = engine_for(
        [uses(call("helper", task="f")), uses(call("lookup", key="k")), says("f"), says("e")]
    )
    start = context(project="p")
    await engine.run(Lead(), start)
    EXECUTED.clear()
    log = []
    await Engine.replay(engine.store, start.run_id, replayed=log)
    assert EXECUTED == [] and sum(e.type == "llm.completed" for e in log) == 2
    await Engine.replay(engine.store, start.run_id, replayed=log, workspace=MemoryWorkspace())
    assert EXECUTED == ["lookup"]


async def test_a_run_without_a_script_raises_a_replay_error_naming_it():
    """A nested run that was not matched to a recorded one is a ReplayError, not a KeyError."""
    from geomind.engine.replay import _Recording

    script = [uses(call("helper", task="find")), says("found"), says("end")]
    result, engine, _ = await run(script, agent=Lead())
    nested = nested_ids(engine.store.load_events(result.run_id))[0]
    original = _Recording.before_llm_call

    def without_script(self, context, agent, messages):
        self.scripts.pop(nested, None)
        return original(self, context, agent, messages)

    _Recording.before_llm_call = without_script
    try:
        with pytest.raises(ReplayError, match=f"run {nested} \\(.*helper"):
            await Engine.replay(engine.store, result.run_id)
    finally:
        _Recording.before_llm_call = original


async def test_nested_runs_reused_are_reported():
    """A run with a project replayed without a workspace says its nested runs were reused."""
    from geomind.engine.replay import nested_runs_reused
    from geomind.stores import MemoryWorkspace

    engine = engine_for([uses(call("helper", task="f")), says("f"), says("e")])
    start = context(project="p")
    await engine.run(Lead(), start)
    events = engine.store.load_events(start.run_id)
    assert nested_runs_reused(events, None)
    assert not nested_runs_reused(events, MemoryWorkspace())
    plain, plain_engine, plain_events = await run([says("e")])
    assert not nested_runs_reused(plain_events, None)


class OtherVersion(Rewriting):
    """Change one recorded output and record the log as another geomind version wrote it."""

    def __init__(self, versions):
        """Keep the versions the run.started events will carry."""
        super().__init__()
        self.versions = versions

    def load_events(self, run_id):
        """Return the changed events with the versions of the old log."""
        return [
            e.model_copy(update={"versions": self.versions}) if isinstance(e, RunStarted) else e
            for e in super().load_events(run_id)
        ]


@pytest.mark.parametrize("versions", [{}, {"geomind": "0.0.1", "gemini": "0.5.0"}])
async def test_a_log_of_another_geomind_version_reuses_the_recorded_tool_results(versions):
    """A log without versions or of another geomind checks the decisions, not the tools' outputs.

    NOTE: the changed output stands for a tool whose result or input form changed between
    versions; the replay does not run it and still compares the completions, calls and answer.
    """
    store = OtherVersion(versions)
    result, engine, _ = await run([says("x")], store=store)
    result, engine, _ = await run([uses(call("lookup", key="k")), says("end")], store=store)
    EXECUTED.clear()
    replayed = await Engine.replay(engine.store, result.run_id)
    assert (replayed.answer, EXECUTED) == ("end", [])


async def test_a_log_of_another_version_still_fails_on_a_changed_answer():
    """The answers are still compared, so a different end is a mismatch."""
    result, engine, events = await run([uses(call("lookup", key="k")), says("end")])
    engine.store.events[result.run_id] = [
        (
            e.model_copy(update={"versions": {}})
            if isinstance(e, RunStarted)
            else e.model_copy(update={"answer": "other"}) if isinstance(e, RunFinished) else e
        )
        for e in events
    ]
    with pytest.raises(ReplayError):
        await Engine.replay(engine.store, result.run_id)


async def test_a_reused_call_is_not_validated_against_the_schema_of_today():
    """An old input that fails the schema of the tool now is not a validation failure here."""
    result, engine, events = await run(
        [uses(call("add", left=1, right=2)), says("end")], store=MemoryRunStore()
    )
    engine.store.events[result.run_id] = [
        (
            e.model_copy(update={"versions": {}})
            if isinstance(e, RunStarted)
            else e.model_copy(update={"input": {"left": 1}}) if isinstance(e, ToolRecorded) else e
        )
        for e in events
    ]
    replayed = []
    await Engine.replay(engine.store, result.run_id, replayed=replayed)
    recorded = [e for e in replayed if isinstance(e, ToolRecorded) and e.tool == "add"]
    assert [(e.input, e.output, e.is_error, e.is_validation) for e in recorded] == [
        ({"left": 1}, 3, False, False)
    ]


class Stater(Worker):
    """Has ``update_state`` beside the pure tools."""

    def __init__(self):
        """Add the tool."""
        super().__init__()
        self.update_state = update_state


async def test_a_state_change_beside_a_reused_call_is_applied_once():
    """A pure call beside ``update_state`` in one step does not get its change applied twice."""
    change = {"op": "replace", "path": "/goal", "value": "cover the peak"}
    result, engine, events = await run(
        [
            uses(call("add", "a", left=1, right=2), call("update_state", "b", changes=[change])),
            says("end"),
        ],
        agent=Stater(),
    )
    engine.store.events[result.run_id] = [
        e.model_copy(update={"versions": {}}) if isinstance(e, RunStarted) else e for e in events
    ]
    replayed = []
    await Engine.replay(engine.store, result.run_id, replayed=replayed)
    assert len([e for e in replayed if isinstance(e, StateChanged)]) == 1


def ended(result):
    """Return how a run ended: status, stop reason, answer and message."""
    return result.status, result.stop_reason, result.answer, result.message


async def test_a_token_budget_stop_replays():
    """A run the budget stopped ends the same in its replay, partial answer included."""
    script = [uses(call("lookup", key="k")), says("never reached")]
    result, engine, _ = await run(script, hooks=[TokenBudget(1)])
    assert result.stop_reason == "denied" and "partial answer" in result.answer
    replayed = await Engine.replay(engine.store, result.run_id)
    assert ended(replayed) == ended(result)


async def test_a_time_limit_stop_replays():
    """A run the clock stopped ends the same, whatever the clock says now."""
    ticks = iter([0.0, 0.0, 100.0, 100.0])
    script = [uses(call("lookup", key="k")), says("never reached")]
    limit = TimeLimit(1, clock=lambda: next(ticks, 100.0))
    result, engine, _ = await run(script, hooks=[limit])
    assert result.stop_reason == "denied"
    replayed = await Engine.replay(engine.store, result.run_id)
    assert ended(replayed) == ended(result)


async def test_a_question_in_auto_mode_replays():
    """A run waiting on ``ask_user`` waits again on the same question."""
    result, engine, _ = await run([uses(call("ask_user", question="Which demand?"))])
    assert result.status == "waiting"
    replayed = await Engine.replay(engine.store, result.run_id)
    assert replayed.status == "waiting"
    assert replayed.request.message == result.request.message


async def test_a_step_limit_replays():
    """A run that hit its step limit ends there again, with the same partial answer."""
    script = [uses(call("lookup", "c1", key="k")), uses(call("lookup", "c2", key="j"))]
    ask = Permissions(mode="ask")  # QA-086: in auto mode the run continues by itself
    result, engine, _ = await run(script, max_steps=1, permissions=ask)
    result = await stopped_at_limit(engine, result)
    assert result.stop_reason == "step_limit"
    replayed = await Engine.replay(engine.store, result.run_id)
    assert ended(replayed) == ended(result)


async def test_an_answered_question_replays():
    """The recorded answer is reused, and the run ends as it did."""
    script = [uses(call("ask_user", question="Which demand?")), says("thanks")]
    result, engine, _ = await run(script)
    resumed = await engine.resume(result.run_id, result.request.id, {"text": "5 MW"})
    replayed = await Engine.replay(engine.store, result.run_id)
    assert replayed.answer == resumed.answer


class Searcher(Agent):
    """Searches the project's documents and asks the user."""

    def __init__(self):
        """Declare the tools."""
        super().__init__()

        # Tools
        from geomind.tools import ask_user, finish, search_rag

        self.search_rag = search_rag
        self.ask_user = ask_user
        self.finish = finish

        # Model
        self.model = Model("fake/model")


async def test_a_resumed_run_with_a_search_made_again_replays():
    """#131: a resumed run whose search_rag notes "already searched" replays, every time.

    ``geomind replay`` of the resumed end-to-end run failed on that note; it now follows the run's
    conversation, which a resume and a replay rebuild.
    """
    from geomind.stores import MemoryWorkspace

    documents = {"p1": [{"id": "a", "title": "Air", "text": "the site air pressure"}]}
    completions = [
        uses(call("search_rag", query="site air pressure")),
        uses(call("ask_user", question="Is there an air pressure?")),
        uses(
            call("search_rag", "c1", query="site.air.pressure atmospheric pressure site"),
            call("search_rag", "c2", query="atmospheric pressure air pressure site"),
            call("search_rag", "c3", query="pressure air site"),
        ),
        says("unknown"),
    ]
    engine = engine_for(completions, workspace=MemoryWorkspace(documents=documents))
    start = context(project="p1")
    paused = await engine.run(Searcher(), start)
    resumed = await engine.resume(start.run_id, paused.request.id, {"text": "unknown"})
    notes = [
        item.output.get("note", "")
        for item in engine.store.load_events(start.run_id)
        if isinstance(item, ToolRecorded) and item.tool == "search_rag"
    ]
    assert ["already searched" in note for note in notes] == [False, False, True, True]
    for _ in range(3):
        replayed = await Engine.replay(
            engine.store, start.run_id, workspace=MemoryWorkspace(documents=documents)
        )
        assert replayed.answer == resumed.answer == "unknown"


def test_a_replay_reads_the_recorded_index_without_what_it_makes_again():
    """The recorded ``results.index`` is the one of the end; a listing at a step is not.

    NOTE: a replay of ``challenge2/colder_reservoir`` listed at step 7 a result the run made
    later, so its ``unknown_name`` message differed from the recorded one.
    """
    from geomind.engine.replay import _ReplayStore

    original = MemoryRunStore()
    original.save_chat_artifact("chat", "results.index", {"references": ["result/a", "result/b"]})
    original.save_chat_artifact("chat", "studies.index", {"studies": [{"study": "study/s"}]})
    original.save_chat_artifact("chat", "result/b", {"kept": True})
    store = _ReplayStore(original, "run", "chat", frozenset({"result/b", "study/s"}))
    assert store.load_chat_artifact("chat", "results.index") == {"references": ["result/a"]}
    assert store.load_chat_artifact("chat", "studies.index") == {"studies": []}
    assert store.load_chat_artifact("chat", "result/b") == {"kept": True}
    store.save_chat_artifact("chat", "results.index", {"references": ["result/a", "result/b"]})
    assert store.load_chat_artifact("chat", "results.index")["references"][-1] == "result/b"


def test_the_references_a_tool_output_holds_are_found_at_any_depth():
    """A reference is a whole string ``<kind>/<name>``; other text is not one."""
    from geomind.tools.gemini.references import references_in

    output = {"result": "result/3f9a", "runs": [{"design": "design/d1"}], "note": "see result/x"}
    assert references_in(output) == {"result/3f9a", "design/d1"}


@pytest.mark.parametrize(
    ("versions", "named"),
    [
        ({}, "an unrecorded version \\(0\\.3\\.0\\)"),
        ({"geomind": "0.4.22.dev6"}, "0\\.4\\.22\\.dev6"),
    ],
)
async def test_a_log_before_the_case_lead_that_differs_says_it_cannot_be_re_run(versions, named):
    """A log older than the case lead is read, not re-run: the error says so and keeps the cause."""
    result, engine, events = await run([uses(call("lookup", key="k")), says("end")])
    engine.store.events[result.run_id] = [
        (
            e.model_copy(update={"versions": versions})
            if isinstance(e, RunStarted)
            else e.model_copy(update={"answer": "other"}) if isinstance(e, RunFinished) else e
        )
        for e in events
    ]
    message = (
        rf"recorded by geomind {named} before the case lead \(0\.4\.22\.dev7\); it can be read, "
        r"shown and exported, but not re-run \(first difference: replay: run .*'other'"
    )
    with pytest.raises(ReplayError, match=message):
        await Engine.replay(engine.store, result.run_id)


@pytest.mark.parametrize("version", ["0.4.22.dev7", "0.4.22.dev63", "0.4.22", "0.5.0"])
async def test_a_log_since_the_case_lead_that_differs_keeps_its_own_message(version):
    """From the case lead on, a difference is the plain mismatch."""
    result, engine, events = await run([says("end")])
    engine.store.events[result.run_id] = [
        (
            e.model_copy(update={"versions": {"geomind": version}})
            if isinstance(e, RunStarted)
            else e.model_copy(update={"answer": "other"}) if isinstance(e, RunFinished) else e
        )
        for e in events
    ]
    with pytest.raises(ReplayError, match=r"^replay: run .*recorded answer 'other'"):
        await Engine.replay(engine.store, result.run_id)
