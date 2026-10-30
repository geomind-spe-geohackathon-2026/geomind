"""A custom loop keeps its place across a pause."""

import pytest

from geomind.engine import Engine, Permissions
from geomind.engine.recovery import recover
from geomind.loops import Loop
from geomind.providers import FakeLLM
from tests.fixtures.runs import Worker, call, context, says, uses


class Counting(Loop):
    """Keep a position in its state."""

    name = "counting"

    def __init__(self):
        """Start at the first round."""
        self.round = 1

    async def run(self, engine, task):
        """Run the agent at a later round."""
        self.round = 3
        return await engine.run(Worker(), task, loop=self)

    def state_dict(self):
        """Return the position."""
        return {"round": self.round}

    def load_state_dict(self, state):
        """Take the position."""
        self.round = state["round"]


def test_base_needs_a_run():
    """A loop has to say what it does."""
    with pytest.raises(NotImplementedError):
        Loop().run(None, None).send(None)


async def test_loop_state_is_saved_and_comes_back_in_another_process():
    """A pause inside a loop resumes at the same place."""
    script = [uses(call("save_note", text="x")), says("end")]
    engine = Engine(llm=FakeLLM(script), permissions=Permissions(mode="ask"))
    start = context()
    loop = Counting()
    paused = await loop.run(engine, start)
    saved = recover(engine.store.load_events(start.run_id))
    assert saved.loop_state == {"round": 3}
    assert saved.loop == "counting"

    fresh = Counting()
    final = await fresh.resume(engine, start.run_id, paused.request.id, {"approved": True})
    assert final.answer == "end" and fresh.round == 3


async def test_loop_state_follows_the_steps():
    """A position that changes during a run is logged when its step ends."""

    class Moving(Counting):
        def state_dict(self):
            self.round += 1
            return super().state_dict()

    engine = Engine(llm=FakeLLM([uses(call("lookup", key="k")), says("end")]))
    start = context()
    await Moving().run(engine, start)
    assert recover(engine.store.load_events(start.run_id)).loop_state == {"round": 6}
