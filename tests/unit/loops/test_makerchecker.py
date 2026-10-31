"""``MakerCheckerLoop``: its final constructor."""

import pytest

from geomind.errors import NotImplementedYet
from geomind.loops import MakerCheckerLoop
from tests.fixtures.runs import Worker


def test_the_constructor_is_final():
    """Two agents and a limit; a run starts with the first."""
    first = Worker()
    loop = MakerCheckerLoop(maker=first, checker=Worker())
    assert (loop.name, loop.agent, loop.max_rounds) == ("makerchecker", first, 3)


async def test_it_comes_in_s3():
    """Running it says so."""
    with pytest.raises(NotImplementedYet, match="MakerCheckerLoop comes in S3"):
        await MakerCheckerLoop(Worker(), Worker()).run(None, None)
