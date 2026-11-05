"""The step-limit question keeps its shape: the backend knows it by it (backend 1.1.7).

The backend takes typed text for any question with options except this one, which it
recognises by options exactly ``[continue, stop]`` and no call id; no new marker is added.
"""

from geomind.engine import Permissions
from tests.fixtures.runs import Worker, call, context, engine_for, uses


async def test_the_step_limit_question_is_continue_or_stop_with_no_call():
    """A run at its step limit asks with options exactly continue and stop, from no call.

    The run asks: in auto mode it continues by itself (QA-086).
    """
    script = [uses(call("lookup", f"c{n}", key="k")) for n in range(4)]
    engine = engine_for(script, permissions=Permissions(mode="ask"))
    start = context()
    result = await engine.run(Worker(), start, max_steps=2)
    assert result.status == "waiting"
    assert result.request.kind == "question"
    assert [option.value for option in result.request.options] == ["continue", "stop"]
    assert [option.label for option in result.request.options] == ["continue", "stop"]
    [event] = [e for e in engine.store.load_events(start.run_id) if e.type == "request"]
    assert event.call is None and event.data().get("call_id") is None
