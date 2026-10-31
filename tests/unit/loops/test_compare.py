"""``CompareLoop``: its final constructor."""

import pytest

from geomind.errors import NotImplementedYet
from geomind.loops import CompareLoop, DesignLoop
from tests.fixtures.runs import Worker


def test_the_constructor_is_final():
    """An inner loop, the alternatives and the criteria; a run starts with the inner agent."""
    inner = DesignLoop(Worker(), Worker())
    loop = CompareLoop(loop=inner, alternatives=("a", "b"), criteria=("cost",))
    assert (loop.name, loop.agent, loop.alternatives) == ("compare", inner.agent, ("a", "b"))


async def test_it_comes_in_s4():
    """Running it says so."""
    with pytest.raises(NotImplementedYet, match="CompareLoop comes in S4"):
        await CompareLoop(DesignLoop(Worker(), Worker()), (), ()).run(None, None)
