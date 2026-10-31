"""The problem state through a whole run: events, recovery, replay and a chat."""

from geomind.agents import Agent
from geomind.engine import Context, Engine, Permissions
from geomind.engine.recovery import recover
from geomind.prompts import Prompt
from geomind.providers import FakeLLM
from geomind.run import Run
from geomind.stores import MemoryRunStore
from geomind.tools import Delegate, update_state
from geomind.types import Message
from tests.fixtures.runs import call, of_type, says, uses

GOAL = {"op": "replace", "path": "/goal", "value": "Size the pump"}
ITEM = {"id": "A1", "text": "Depth", "value": 2000, "source": "user"}
ADD = {"op": "add", "path": "/assumptions/-", "value": ITEM}
CONFIRM = {"op": "replace", "path": "/assumptions/A1/confirmed", "value": True}


class Noter(Agent):
    """Takes notes."""

    def __init__(self):
        """Declare the note tool."""
        super().__init__()

        # Prompt
        self.prompt = Prompt.text("Take notes.")

        # Tools
        self.update_state = update_state


class Lead(Noter):
    """Delegates to a noter."""

    def __init__(self):
        """Add the delegate."""
        super().__init__()

        # Tools
        self.helper = Delegate(Noter())


def note(*changes, call_id="c1"):
    """Return a completion that changes the state."""
    return uses(call("update_state", call_id, changes=list(changes)))


def chat_run(store, llm, message, permissions=None):
    """Return a run of the chat ``c``."""
    return Run(
        message,
        chat="c",
        llm=llm,
        store=store,
        permissions=permissions or Permissions("auto"),
        agent=Noter(),
    )


async def run_engine(script, agent=None, **options):
    """Run a script; return the engine and the context."""
    engine = Engine(llm=FakeLLM(script), permissions=Permissions("auto"), **options)
    start = Context(messages=[Message(role="user", content="go")])
    await engine.run(agent or Noter(), start)
    return engine, start


async def test_each_change_is_one_event_with_the_next_version():
    """``state.changed`` is the JSON of the contract, starting at 1."""
    engine, start = await run_engine([note(GOAL), note(ADD, CONFIRM, call_id="c2"), says()])
    events = of_type(engine.store.load_events(start.run_id), "state.changed")
    assert [event.data()["version"] for event in events] == [1, 2]
    assert events[1].data()["changes"] == [ADD, CONFIRM]


async def test_the_model_reads_the_state_last_and_never_in_the_history():
    """The state is the last message of a call and leaves no trace in the conversation."""
    engine, _ = await run_engine([note(GOAL), note(ADD, call_id="c2"), says()])
    last, third = engine.llm.llm.calls[1]["messages"], engine.llm.llm.calls[2]["messages"]
    assert last[-1].content == "Problem state, version 1\nGoal: Size the pump"
    assert third[-1].content.startswith("Problem state, version 2")
    assert sum("Problem state" in message.content for message in third) == 1


async def test_an_invalid_patch_is_a_result_and_changes_nothing():
    """The model reads how to fix it; no event is logged."""
    script = [note({"op": "remove", "path": "/questions/Q1"}), says()]
    engine, start = await run_engine(script)
    events = engine.store.load_events(start.run_id)
    assert of_type(events, "state.changed") == []
    output = of_type(events, "tool.result")[0].output
    assert output["error"]["code"] == "invalid_input"


async def test_recover_rebuilds_the_state_from_the_events():
    """The log alone gives the state, at the same version."""
    engine, start = await run_engine([note(GOAL), note(ADD, call_id="c2"), says()])
    state = recover(engine.store.load_events(start.run_id))
    assert (state.problem.version, state.problem.goal) == (2, "Size the pump")
    assert state.problem.assumptions[0].id == "A1"


async def test_a_replay_rebuilds_the_state_too():
    """A replay reruns the notes, so what it sends the model holds them."""
    engine, start = await run_engine([note(GOAL), says("done")])
    result = await Engine.replay(engine.store, start.run_id)
    assert result.answer == "done"


async def test_a_nested_run_shares_the_state():
    """A change in a child reaches the parent and the rebuilt log."""
    script = [
        uses(call("helper", "c1", task="note it")),
        note(GOAL, call_id="n1"),
        says("noted"),
        note(ADD, call_id="c2"),
        says("end"),
    ]
    engine, start = await run_engine(script, Lead())
    events = engine.store.load_events(start.run_id)
    assert [event.version for event in of_type(events, "state.changed")] == [1, 2]
    assert recover(events).problem.goal == "Size the pump"


async def test_a_run_without_a_chat_saves_no_state():
    """Only a chat has a state to keep."""
    engine, _ = await run_engine([note(GOAL), says()])
    assert engine.store.states == {}


def test_the_state_persists_across_two_messages_of_a_chat():
    """The next message continues the versions and the model sees the first note."""
    store = MemoryRunStore()
    chat_run(store, FakeLLM([note(GOAL), says()]), "first").start()
    assert store.load_state("c")["version"] == 1
    second = FakeLLM([note(ADD), says()])
    chat_run(store, second, "second").start()
    assert second.calls[0]["messages"][-1].content.endswith("Goal: Size the pump")
    assert (store.load_state("c")["version"], store.load_state("c")["goal"]) == (2, "Size the pump")
    assert store.load_state("c")["assumptions"][0]["id"] == "A1"


def test_notes_need_no_approval_in_ask_mode():
    """``update_state`` only touches the run's own notes."""
    store = MemoryRunStore()
    result = chat_run(store, FakeLLM([note(GOAL), says()]), "go", Permissions("ask")).start()
    assert result.status == "done"
    permission = of_type(store.load_events(result.run_id), "permission")[0]
    assert permission.rule == "allow:update_state"


def test_an_ask_rule_still_wins_over_the_default():
    """A caller who wants to approve notes can."""
    store = MemoryRunStore()
    permissions = Permissions("ask", ask=["update_state"])
    result = chat_run(store, FakeLLM([note(GOAL)]), "go", permissions).start()
    assert result.status == "waiting"


def test_readonly_refuses_notes():
    """``readonly`` keeps its promise: nothing is written."""
    store = MemoryRunStore()
    chat_run(store, FakeLLM([note(GOAL), says()]), "go", Permissions("readonly")).start()
    assert store.load_state("c")["version"] == 0
