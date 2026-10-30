"""The order of writes."""

import pytest

from swarmax import runtime
from swarmax.agents import Agent
from swarmax.engine import Context, Engine, Permissions
from swarmax.engine.store import MemoryRunStore
from swarmax.providers import FakeLLM
from swarmax.tools import tool
from swarmax.types import ToolCall
from tests.fixtures.runs import Worker, call, context, engine_for, of_type, run, says, types, uses


class FailingStore(MemoryRunStore):
    """Fail on one event type."""

    def __init__(self, kind):
        """Remember the type to fail on."""
        super().__init__()
        self.kind = kind

    def save_event(self, run_id, event):
        """Raise instead of saving."""
        if event.type == self.kind:
            raise KeyboardInterrupt
        super().save_event(run_id, event)


async def test_sequence_is_gapless():
    """Every event has the next number."""
    _, _, events = await run([uses(call("lookup", key="a")), says()])
    assert [event.sequence for event in events] == list(range(1, len(events) + 1))


async def test_a_completion_is_logged_before_its_tools_run():
    """The completion precedes the tool, and a failed save means the tool never starts."""
    store = FailingStore("llm.completed")
    engine = engine_for([uses(call("lookup", key="a"))], store=store)
    with pytest.raises(KeyboardInterrupt):
        await engine.run(Worker(), context())
    assert "tool.started" not in types(next(iter(store.events.values())))


async def test_a_result_is_logged_before_the_next_call():
    """The next LLM call happens only after the result is saved."""
    _, _, events = await run([uses(call("lookup", key="a")), says()])
    order = types(events)
    assert order.index("tool.result") < order.index("llm.completed", order.index("tool.result"))


async def test_text_is_logged_before_its_completion():
    """Deltas keep their place, in order."""
    _, _, events = await run([says("hi")])
    order = types(events)
    assert order.index("text.delta") < order.index("llm.completed")
    assert of_type(events, "text.delta")[0].text == "hi"


async def test_known_secrets_never_reach_the_store():
    """A key in a message, a tool call or an answer is redacted everywhere."""

    class Keyed(FakeLLM):
        secrets = ("sk-secret",)

    script = [uses(ToolCall(id="c", name="lookup", input={"key": "sk-secret"})), says("sk-secret")]
    engine = Engine(llm=Keyed(script), permissions=Permissions(mode="auto"))
    start = Context(messages=[])
    result = await engine.run(Worker(), start)
    stored = "".join(event.model_dump_json() for event in engine.store.load_events(start.run_id))
    assert "sk-secret" not in stored and "[redacted]" in stored
    assert "sk-secret" not in str(engine.store.load_checkpoint(start.run_id))
    assert result.answer == "[redacted]"


class Streaming(FakeLLM):
    """Stream a text in fixed pieces."""

    secrets = ("sk-SECRET-123",)

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Split the text in the middle of the secret."""
        on_text("key sk-SEC")
        on_text("RET-123 end")
        return await super().complete(messages, tools, model=model, settings=settings)


async def test_a_secret_split_across_deltas_never_streams():
    """Text is held back just long enough to see a secret whole; nothing is lost."""
    llm = Streaming([says("key sk-SECRET-123 end")])
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"))
    start = Context(messages=[])
    await engine.run(Worker(), start)
    text = "".join(
        event.text for event in of_type(engine.store.load_events(start.run_id), "text.delta")
    )
    assert "sk-SEC" not in text and text == "key [redacted] end"


@tool(effect="read")
def leak():
    """Return a secret, as a tool that reads a settings file could."""
    return "sk-SECRET-123 " * 10


class Leaking(Agent):
    """Has the leaking tool."""

    def __init__(self):
        """Declare the tool."""
        super().__init__()

        # Tools
        self.leak = leak


async def test_a_secret_never_reaches_an_artifact():
    """Large results are stored under the same rule as events."""
    llm = Streaming([uses(ToolCall(id="c", name="leak")), says()])
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"))
    start = Context(messages=[])
    with runtime.settings(tool_result_limit=10):
        await engine.run(Leaking(), start)
    assert engine.store.artifacts
    assert "sk-SECRET-123" not in str(engine.store.artifacts)
