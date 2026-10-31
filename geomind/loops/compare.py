"""Run a loop on alternatives and rank them."""

from geomind.errors import NotImplementedYet
from geomind.loops.loop import Loop


class CompareLoop(Loop):
    """Run ``loop`` on each of ``alternatives`` and rank the results on ``criteria``."""

    name = "compare"

    def __init__(self, loop, alternatives, criteria):
        """Keep the inner loop, what to compare and how; a run starts with its agent."""
        self.loop = loop
        self.agent = loop.agent
        self.alternatives = alternatives
        self.criteria = criteria

    async def run(self, engine, task):
        """Drive the alternatives from the context ``task``."""
        raise NotImplementedYet("CompareLoop comes in S4")
