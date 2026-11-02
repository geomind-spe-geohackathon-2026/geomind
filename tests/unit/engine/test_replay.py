"""Replay: offline, faithful, and honest about differences."""

import asyncio

import pytest

from geomind.agents import Agent, Model
from geomind.engine import Engine, Permissions
from geomind.engine.hooks import Hook, RequireApproval
from geomind.engine.replay import _nested_changes, version_differences
from geomind.engine.session import current_versions
from geomind.errors import ReplayError
from geomind.stores.run import MemoryRunStore
from geomind.tools import Delegate, tool, update_state
from geomind.types import Action, Deny, Message, ToolCall
from geomind.types.events import RunStarted, StateChanged, ToolRecorded, ToolStarted
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
    """A replay ends where the log ends."""
    result, engine, _ = await run(
        [uses(call("save_note", text="x"))], hooks=[RequireApproval(["save_note"])]
    )
    EXECUTED.clear()
    replayed = await Engine.replay(engine.store, result.run_id)
    assert EXECUTED == [] and replayed.stop_reason == "cancelled"


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
    assert [change[0]["value"]["by"] for change in changes["a"]] == ["from a"]
    assert [change[0]["value"]["by"] for change in changes["b"]] == ["from b"]


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

    assert _children(delegated_log(), "root") == {"a": "child-a", "b": "child-b"}


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
