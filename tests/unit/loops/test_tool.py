"""One run of one agent."""

import pytest

from swarmax.engine import Engine
from swarmax.errors import LoopError
from swarmax.loops import ToolLoop
from swarmax.providers import FakeLLM
from tests.fixtures.runs import Worker, call, context, of_type, says, uses


async def test_run_reports_the_loop_name():
    """The contract's ``run.started`` names the loop."""
    engine = Engine(llm=FakeLLM([says("end")]))
    start = context()
    result = await ToolLoop(Worker()).run(engine, start)
    assert result.answer == "end"
    event = of_type(engine.store.load_events(start.run_id), "run.started")[0]
    assert event.data()["loop"] == "tool"


async def test_max_steps_is_passed_on():
    """The loop owns the limit."""
    engine = Engine(llm=FakeLLM([uses(call("lookup", key="k"))]))
    result = await ToolLoop(Worker(), max_steps=1).run(engine, context())
    assert result.stop_reason == "step_limit"


def test_state_of_another_agent_is_refused():
    """A checkpoint fits one agent."""
    with pytest.raises(LoopError, match="expected 'worker'"):
        ToolLoop(Worker()).load_state_dict({"agent": "other"})
