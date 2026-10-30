"""The small parts of delegation; ``tests/integration/test_delegate.py`` runs the whole."""

from geomind.engine import Engine, Permissions
from geomind.engine.delegation import run_child
from geomind.providers import FakeLLM
from tests.fixtures.runs import Helper, Lead, call, context, of_type, says, uses


async def test_run_child_shares_the_log_of_its_parent():
    """A delegate call goes through ``run_child`` and lands in the root's log."""
    engine = Engine(
        llm=FakeLLM([uses(call("helper", task="t")), says("found"), says("end")]),
        permissions=Permissions(mode="auto"),
    )
    start = context()
    await engine.run(Lead(), start)
    started = of_type(engine.store.load_events(start.run_id), "run.started")
    assert [event.parent for event in started] == [None, start.run_id]
    assert isinstance(Lead().helper_agent, Helper) and callable(run_child)
