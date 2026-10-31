"""Propose, simulate, verify and repeat until a design passes."""

from geomind.errors import NotImplementedYet
from geomind.loops.loop import Loop


class DesignLoop(Loop):
    """Let ``designer`` propose and ``verifier`` check, for at most ``max_rounds`` rounds."""

    name = "design"

    def __init__(self, designer, verifier, max_rounds=5):
        """Keep the two agents and the limit; a run starts with the designer."""
        self.agent = designer
        self.verifier = verifier
        self.max_rounds = max_rounds

    async def run(self, engine, task):
        """Drive the rounds from the context ``task``."""
        raise NotImplementedYet("DesignLoop comes in S3")
