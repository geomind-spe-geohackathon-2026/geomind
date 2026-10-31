"""Replay: offline, faithful, and honest about differences."""

import pytest

from geomind.agents import Agent
from geomind.engine import Engine, Permissions
from geomind.engine.hooks import Hook, RequireApproval
from geomind.errors import ReplayError
from geomind.stores.run import MemoryRunStore
from geomind.tools import Delegate, tool, update_state
from geomind.types import Action, Deny, ToolCall
from geomind.types.events import ToolRecorded
from tests.fixtures.runs import EXECUTED, Worker, call, context, engine_for, lookup, run, says, uses


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
