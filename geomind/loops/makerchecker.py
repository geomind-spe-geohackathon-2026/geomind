"""One agent proposes and another checks."""

from geomind.errors import NotImplementedYet
from geomind.loops.loop import Loop


class MakerCheckerLoop(Loop):
    """Let ``maker`` propose and ``checker`` review, for at most ``max_rounds`` rounds."""

    name = "makerchecker"

    def __init__(self, maker, checker, max_rounds=3):
        """Keep the two agents and the limit; a run starts with the maker."""
        self.agent = maker
        self.checker = checker
        self.max_rounds = max_rounds

    async def run(self, engine, task):
        """Drive the rounds from the context ``task``."""
        raise NotImplementedYet("MakerCheckerLoop comes in S3")
