"""``TimeLimit`` bounds the call in flight: a model call or an async tool stops at the limit."""

import asyncio
import threading
from time import perf_counter

from geomind.engine import Engine, Permissions
from geomind.engine.hooks import TimeLimit
from geomind.providers import FakeLLM
from geomind.tools import tool
from tests.fixtures.runs import Worker, call, context, says, uses

RELEASED = threading.Event()


class SlowLLM(FakeLLM):
    """Answer after ``seconds``, as a provider that hangs."""

    def __init__(self, completions, seconds):
        """Keep the script and the delay."""
        super().__init__(completions)
        self.seconds = seconds

    async def complete(self, messages, tools, *, model, settings, on_text=None):
        """Wait, then answer from the script."""
        await asyncio.sleep(self.seconds)
        return await super().complete(messages, tools, model=model, settings=settings)


@tool(effect="read")
async def wait_long(seconds: float):
    """Wait, as a long async tool does."""
    await asyncio.sleep(seconds)
    return "waited"


@tool(effect="read")
def block_long(seconds: float):
    """Block a worker thread, as a long gemini computation does."""
    RELEASED.wait(seconds)
    return "blocked"


class Waiter(Worker):
    """A worker with the long tools."""

    def __init__(self):
        """Declare the tools."""
        super().__init__()
        self.wait_long = wait_long
        self.block_long = block_long


async def timed(llm, agent=None, limit=0.2):
    """Run under a time limit; return the result and the seconds it took."""
    engine = Engine(llm=llm, permissions=Permissions(mode="auto"), hooks=[TimeLimit(limit)])
    started = perf_counter()
    result = await engine.run(agent or Worker(), context())
    return result, perf_counter() - started


async def test_a_model_call_in_flight_stops_at_the_limit():
    """A provider that hangs past the limit is cancelled; the run gives its partial answer."""
    result, seconds = await timed(SlowLLM([says("late")], 5.0))
    assert seconds < 2.0
    assert result.stop_reason == "denied" and "time limit" in result.message
    assert "partial answer" in result.answer


async def test_an_async_tool_in_flight_stops_at_the_limit():
    """A tool that runs past the limit is cancelled, and the next model call is denied."""
    script = [uses(call("wait_long", seconds=5.0)), says("never")]
    result, seconds = await timed(FakeLLM(script), Waiter())
    assert seconds < 2.0
    assert result.stop_reason == "denied" and "time limit" in result.message


async def test_a_thread_cannot_be_cancelled_but_the_run_stops_waiting():
    """A sync tool's thread runs on to its end; the run ends at the limit all the same."""
    RELEASED.clear()
    script = [uses(call("block_long", seconds=5.0)), says("never")]
    result, seconds = await timed(FakeLLM(script), Waiter())
    RELEASED.set()
    assert seconds < 2.0
    assert result.stop_reason == "denied"


async def test_a_call_inside_the_limit_is_untouched():
    """A call that ends in time ends as without a limit."""
    result, _ = await timed(SlowLLM([says("on time")], 0.01), limit=5.0)
    assert result.answer == "on time"
