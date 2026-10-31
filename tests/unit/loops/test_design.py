"""``DesignLoop``: its final constructor."""

import pytest

from geomind.errors import NotImplementedYet
from geomind.loops import DesignLoop
from tests.fixtures.runs import Worker


def test_the_constructor_is_final():
    """Two agents and a limit; a run starts with the first."""
    first = Worker()
    loop = DesignLoop(designer=first, verifier=Worker())
    assert (loop.name, loop.agent, loop.max_rounds) == ("design", first, 5)


async def test_it_comes_in_s3():
    """Running it says so."""
    with pytest.raises(NotImplementedYet, match="DesignLoop comes in S3"):
        await DesignLoop(Worker(), Worker()).run(None, None)
