"""The engine: stop reasons and limits."""

from swarmax.engine import Engine, Permissions
from swarmax.engine.hooks import TokenBudget
from swarmax.errors import ProviderError
from swarmax.providers import FakeLLM
from swarmax.types import Usage
from tests.fixtures.runs import Worker, call, context, of_type, run, says, types, uses


async def test_answer_stops_a_run():
    """No tool calls means the text is the answer."""
    result, _, events = await run([says("hello")])
    assert (result.status, result.stop_reason, result.answer) == ("done", "answer", "hello")
    assert result.steps == 1 and result.usage.input_tokens == 10
    assert types(events)[-1] == "run.finished"


async def test_step_limit_stops_a_run():
    """A run is finite."""
    calls = [uses(call("lookup", f"c{index}", key="k")) for index in range(5)]
    result, _, events = await run(calls, max_steps=2)
    assert (result.status, result.stop_reason, result.steps) == ("failed", "step_limit", 2)
    assert of_type(events, "run.finished")[0].message == "stopped after 2 steps"


async def test_provider_failure_ends_the_run_with_an_error():
    """After the retries the run fails and says why."""
    result, _, events = await run([ProviderError("bad key")])
    assert (result.status, result.stop_reason) == ("failed", "error")
    assert of_type(events, "error")[0].where == "engine"
    assert of_type(events, "run.finished")[0].message == "bad key"


async def test_steps_left_reaches_the_model():
    """The dynamic part counts down."""
    _, engine, _ = await run([uses(call("lookup", key="k")), says()], max_steps=5)
    last = [call_["messages"][-1].content for call_ in engine.llm.llm.calls]
    assert last == ["Steps left: 4", "Steps left: 3"]


async def test_hook_handles_can_be_removed():
    """A removed hook no longer decides."""
    engine = Engine(llm=FakeLLM([says("ok")]))
    handle = engine.register_hook(TokenBudget(0))
    handle.remove()
    assert (await engine.run(Worker(), context())).answer == "ok"


async def test_default_permissions_ask():
    """A new engine asks before anything that changes something."""
    assert Engine().permissions.mode == "ask"
    assert isinstance(Engine().permissions, Permissions)


async def test_usage_event_holds_running_totals():
    """The totals grow step by step."""
    _, _, events = await run([uses(call("lookup", key="k")), says()])
    totals = [event.input_tokens for event in of_type(events, "usage")]
    assert totals == [10, 20]
    step = of_type(events, "step.finished")[1].usage
    assert step == Usage(input_tokens=10, output_tokens=5, cost=0.01)
