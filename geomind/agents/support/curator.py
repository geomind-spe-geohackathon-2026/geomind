"""The agent that keeps the general lessons of a run for each role."""

from geomind import tools
from geomind.agents.agent import Agent, Model
from geomind.prompts import Prompt


class Curator(Agent):
    """Write the general lessons of a run for each role, and the user's facts, into experience.

    NOTE: it writes method in words, with its origin, never a project's numbers as a rule
    (``write_lesson`` refuses a digit in a lesson). An approved design is kept by code alone,
    after the reviewer passed it; the curator never writes one.
    """

    def __init__(self):
        """Declare the prompt, the memory tools and the role's model."""
        super().__init__()

        # Prompt
        self.prompt = Prompt("support/curator")

        # Tools
        self.read_case = tools.gemini.read_case
        self.read_stored = tools.read_stored
        self.search_memory = tools.search_memory
        self.read_memory = tools.read_memory
        self.write_lesson = tools.write_lesson
        self.finish = tools.finish

        # Model
        self.model = Model(setting="curator_model", temperature=0)
